import ast
import io
import json
import os
import re
import threading
import time
import tokenize
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Pattern, Union


def _safe_to_text(x: Any, max_len: int = 200_000) -> str:
    if isinstance(x, str):
        s = x
    else:
        try:
            s = json.dumps(x, ensure_ascii=False, default=str)
        except Exception:
            s = str(x)
    if len(s) > max_len:
        s = s[:max_len] + "...(truncated)"
    return s


_INLINE_FLAG_MAP = {
    "a": re.ASCII,
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
    "u": re.UNICODE,
    "x": re.VERBOSE,
}

_RESOURCE_URL_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s\"'<>)}\]]+",
    flags=re.IGNORECASE,
)
_TRAILING_ESCAPED_WS_RE = re.compile(r"(?:\\[nrt])+$")
_DEFAULT_SCAN_FIELDS = ("action", "info", "response", "a11y_tree")


def _compile_pattern(
    pattern: str,
    *,
    default_flags: int,
    auto_anchor: bool,
) -> Pattern[str]:
    inline_flags = 0
    body = pattern
    inline_match = re.match(r"^\(\?([aiLmsux]+)\)", pattern)
    if inline_match:
        for flag_char in inline_match.group(1):
            inline_flags |= _INLINE_FLAG_MAP.get(flag_char, 0)
        body = pattern[inline_match.end() :]

    if auto_anchor:
        if not body.startswith("^"):
            body = f"^(?:{body})"
        if not body.endswith("$"):
            body = f"{body}$"

    return re.compile(body, flags=default_flags | inline_flags)


def _normalize_observed_url(url: str) -> str:
    normalized = url.strip(" \t\r\n\"'`,.;:!?()[]{}")
    normalized = _TRAILING_ESCAPED_WS_RE.sub("", normalized)
    return normalized


def _normalize_observed_path(path: str) -> str:
    normalized = path.strip(" \t\r\n\"'`,.;:!?()[]{}")
    normalized = _TRAILING_ESCAPED_WS_RE.sub("", normalized)
    if normalized.startswith("~"):
        return "~" + re.sub(r"/{2,}", "/", normalized[1:])
    if normalized.startswith("/"):
        return re.sub(r"/{2,}", "/", normalized)
    return normalized


def _normalize_scan_fields(scan_fields: Optional[List[str]]) -> List[str]:
    if not scan_fields:
        return list(_DEFAULT_SCAN_FIELDS)

    normalized: List[str] = []
    seen = set()
    for field_name in scan_fields:
        clean = str(field_name).strip()
        if not clean:
            continue
        if clean not in _DEFAULT_SCAN_FIELDS:
            raise ValueError(
                f"Unsupported protected monitor scan field: {clean}. "
                f"Expected one of {', '.join(_DEFAULT_SCAN_FIELDS)}."
            )
        if clean in seen:
            continue
        normalized.append(clean)
        seen.add(clean)

    return normalized or list(_DEFAULT_SCAN_FIELDS)


def _iter_target_names(node: ast.AST) -> List[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: List[str] = []
        for elt in node.elts:
            names.extend(_iter_target_names(elt))
        return names
    return []


def _collect_name_refs(node: ast.AST) -> List[str]:
    return sorted(
        {
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name)
        }
    )


def _is_pyautogui_call(node: ast.AST, *, attrs: set[str]) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pyautogui"
        and node.func.attr in attrs
    )


def _preserved_string_lines(source: str) -> set[int]:
    fallback_lines = {
        lineno
        for lineno, line in enumerate(source.splitlines(), start=1)
        if "pyautogui." in line
    }

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return fallback_lines

    preserve_lines = set(fallback_lines)
    typed_arg_names: set[str] = set()

    for node in ast.walk(tree):
        if _is_pyautogui_call(
            node,
            attrs={"typewrite", "write", "press", "hotkey"},
        ):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", start)
            if start is not None:
                preserve_lines.update(range(start, (end or start) + 1))
            if node.args and _is_pyautogui_call(
                node,
                attrs={"typewrite", "write"},
            ):
                typed_arg_names.update(_collect_name_refs(node.args[0]))

    if not typed_arg_names:
        return preserve_lines

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            target_names = {
                name
                for target in node.targets
                for name in _iter_target_names(target)
            }
        elif isinstance(node, ast.AnnAssign):
            target_names = set(_iter_target_names(node.target))
        else:
            continue

        if not target_names.intersection(typed_arg_names):
            continue
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", start)
        if start is not None:
            preserve_lines.update(range(start, (end or start) + 1))

    return preserve_lines


def _strip_python_comments_and_nonexecuted_literals(source: str) -> str:
    preserve_lines = _preserved_string_lines(source)
    try:
        rewritten_tokens = []
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                continue
            if token.type == tokenize.STRING and token.start[0] not in preserve_lines:
                rewritten_tokens.append(token._replace(string="''"))
            else:
                rewritten_tokens.append(token)
        return tokenize.untokenize(rewritten_tokens)
    except (IndentationError, SyntaxError, tokenize.TokenError):
        sanitized = re.sub(
            r"(?s)(\"\"\".*?\"\"\"|'''.*?''')",
            "''",
            source,
        )
        return "\n".join(
            line
            for line in sanitized.splitlines()
            if not line.strip().startswith("#")
        )


def _looks_executable_action_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped in {"WAIT", "DONE", "FAIL"}:
        return True
    if stripped.startswith(("import ", "from ")):
        return True
    if stripped.startswith(
        (
            "if ",
            "elif ",
            "else:",
            "for ",
            "while ",
            "try:",
            "except",
            "with ",
        )
    ):
        return True
    return any(ch in stripped for ch in ("(", ")", "=", "."))


def _canonicalize_action_script(script: str) -> str:
    stripped = script.strip()
    if not stripped:
        return ""
    if stripped in {"WAIT", "DONE", "FAIL"}:
        return stripped

    sanitized = _strip_python_comments_and_nonexecuted_literals(stripped)
    kept_lines = [
        line.rstrip()
        for line in sanitized.splitlines()
        if _looks_executable_action_line(line)
    ]
    return "\n".join(kept_lines).strip()


def canonicalize_action_for_matching(action: Any) -> str:
    if isinstance(action, list):
        parts = [canonicalize_action_for_matching(item) for item in action]
        return "\n\n".join(part for part in parts if part).strip()
    if isinstance(action, tuple):
        return canonicalize_action_for_matching(list(action))
    if isinstance(action, str):
        return _canonicalize_action_script(action)
    return _safe_to_text(action)


@dataclass
class ProtectedResourceMonitor:
    protected: List[str]
    output_path: str
    protected_regex: List[str] = field(default_factory=list)
    use_regex: bool = False
    case_sensitive: bool = False
    regex_fullmatch: bool = True
    regex_anchor_patterns: bool = True
    log_unmatched_steps: bool = False
    policy_name: str = ""
    policy_hypothesis: str = ""
    policy_non_protected_examples: List[str] = field(default_factory=list)
    policy_prompt_injected: Optional[bool] = None
    policy_visibility: str = ""
    policy_enforcement: str = "monitor_only"
    policy_task_tags: List[str] = field(default_factory=list)
    policy_instruction_basis: str = ""
    policy_style: str = ""
    scan_fields: List[str] = field(
        default_factory=lambda: list(_DEFAULT_SCAN_FIELDS)
    )
    policy_kind: str = "resource"
    action_match_mode: str = ""

    _count: int = 0
    _hits: Dict[str, int] = field(default_factory=dict)
    _compiled_literals: List[str] = field(default_factory=list)
    _compiled_regex: List[Pattern[str]] = field(default_factory=list)
    _regex_pattern_map: Dict[str, str] = field(default_factory=dict)
    _normalized_to_original: Dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.scan_fields = _normalize_scan_fields(self.scan_fields)
        self.policy_kind = str(self.policy_kind or "resource")
        self.action_match_mode = str(
            self.action_match_mode
            or ("executable_only" if self.policy_kind == "action" else "raw")
        )
        if self.action_match_mode not in {"raw", "executable_only"}:
            raise ValueError(
                "Unsupported action_match_mode: "
                f"{self.action_match_mode}. Expected 'raw' or 'executable_only'."
            )
        flags = 0 if self.case_sensitive else re.IGNORECASE
        regex_patterns = list(self.protected_regex)
        if self.use_regex:
            regex_patterns = list(self.protected)
            self.protected = []

        if regex_patterns:
            compiled: List[Pattern[str]] = []
            for p in regex_patterns:
                compiled_pattern = _compile_pattern(
                    p,
                    default_flags=flags,
                    auto_anchor=self.regex_anchor_patterns,
                )
                compiled.append(compiled_pattern)
                self._regex_pattern_map[compiled_pattern.pattern] = p
            self._compiled_regex = compiled

        if self.protected:
            self._compiled_literals = [
                p if self.case_sensitive else p.lower() for p in self.protected
            ]
            self._normalized_to_original = {
                (p if self.case_sensitive else p.lower()): p for p in self.protected
            }

        out_dir = os.path.dirname(self.output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    def _match(self, haystack: str) -> List[str]:
        if not haystack:
            return []
        out: List[str] = []
        if self._compiled_literals:
            if not self.case_sensitive:
                h = haystack.lower()
                out.extend(
                    self._normalized_to_original[p]
                    for p in self._compiled_literals
                    if p in h
                )
            else:
                out.extend(
                    self._normalized_to_original.get(p, p)
                    for p in self._compiled_literals
                    if p in haystack
                )

        if not self._compiled_regex:
            return out
        observed = self._extract_observed_resources(haystack)
        units = set(observed["urls"] + observed["paths"] + observed["directories"])
        units.add(haystack)
        units.update(line.strip() for line in haystack.splitlines() if line.strip())
        units.update(
            tok.strip(" \t\r\n\"'`,.;:!?()[]{}")
            for tok in re.findall(r"\S+", haystack)
            if tok.strip(" \t\r\n\"'`,.;:!?()[]{}")
        )

        for p in self._compiled_regex:
            if self.regex_fullmatch:
                matched = any(p.fullmatch(unit) for unit in units)
            else:
                matched = any(p.search(unit) for unit in units)
            if matched:
                out.append(self._regex_pattern_map.get(p.pattern, p.pattern))
        return out

    def _extract_observed_resources(self, text: str) -> Dict[str, List[str]]:
        if not text:
            return {"urls": [], "paths": [], "directories": []}
        raw_urls = _RESOURCE_URL_RE.findall(text)
        urls = sorted(
            {
                normalized
                for url in raw_urls
                if (normalized := _normalize_observed_url(url))
            }
        )
        text_without_urls = text
        for url in raw_urls:
            text_without_urls = text_without_urls.replace(url, " ")
        raw_paths = re.findall(r"(?:~|/)[A-Za-z0-9._/\-]+", text_without_urls)
        paths = sorted(
            set(
                normalized
                for p in raw_paths
                if (normalized := _normalize_observed_path(p))
                and len(normalized) > 1
                and normalized not in {"/"}
            )
        )
        directories = sorted(
            {
                _normalize_observed_path(os.path.dirname(p.rstrip("/")) or "/")
                for p in paths
            }
        )
        return {"urls": urls, "paths": paths, "directories": directories}

    def observe_step(
        self,
        *,
        domain: str,
        example_id: str,
        step_num: int,
        action: Any,
        info: Any,
        response: Optional[Any] = None,
        obs: Optional[Dict[str, Any]] = None,
        when: str = "after_step",
        ts: Optional[float] = None,
    ) -> None:
        ts = ts if ts is not None else time.time()

        blob: Dict[str, Any] = {}
        field_match_bases: Dict[str, str] = {}
        if "action" in self.scan_fields:
            if self.policy_kind == "action" and self.action_match_mode == "executable_only":
                blob["action"] = canonicalize_action_for_matching(action)
                field_match_bases["action"] = "canonical_executable"
            else:
                blob["action"] = action
                field_match_bases["action"] = "raw_text"
        if "info" in self.scan_fields:
            blob["info"] = info
            field_match_bases["info"] = "raw_text"
        if response is not None and "response" in self.scan_fields:
            blob["response"] = response
            field_match_bases["response"] = "raw_text"
        if (
            obs
            and isinstance(obs, dict)
            and "a11y_tree" in self.scan_fields
            and "a11y_tree" in obs
        ):
            blob["a11y_tree"] = obs.get("a11y_tree")
            field_match_bases["a11y_tree"] = "raw_text"
        field_text = {
            key: _safe_to_text(val)
            for key, val in blob.items()
        }
        matched_by_field: Dict[str, List[str]] = {}
        observed_urls: List[str] = []
        observed_paths: List[str] = []
        observed_directories: List[str] = []
        all_matches: List[str] = []
        for key, text in field_text.items():
            field_matches = self._match(text)
            if field_matches:
                matched_by_field[key] = sorted(set(field_matches))
                all_matches.extend(field_matches)
            observed = self._extract_observed_resources(text)
            observed_urls.extend(observed["urls"])
            observed_paths.extend(observed["paths"])
            observed_directories.extend(observed["directories"])
        matched = sorted(set(all_matches))
        if not matched and not self.log_unmatched_steps:
            return

        with self._lock:
            if matched:
                self._count += 1
                for m in matched:
                    self._hits[m] = self._hits.get(m, 0) + 1

            rec = {
                "ts": ts,
                "domain": domain,
                "example_id": example_id,
                "step_num": step_num,
                "when": when,
                "matched": matched,
                "matched_by_field": matched_by_field,
                "observed_urls": sorted(set(observed_urls)),
                "observed_paths": sorted(set(observed_paths)),
                "observed_directories": sorted(set(observed_directories)),
                "total_hits": self._count,
                "per_pattern_hits": dict(self._hits),
                "policy_name": self.policy_name,
                "policy_hypothesis": self.policy_hypothesis,
                "policy_literals": list(self.protected),
                "policy_regex": list(self.protected_regex),
                "policy_non_protected_examples": list(self.policy_non_protected_examples),
                "policy_prompt_injected": self.policy_prompt_injected,
                "policy_visibility": self.policy_visibility,
                "policy_enforcement": self.policy_enforcement,
                "policy_task_tags": list(self.policy_task_tags),
                "policy_instruction_basis": self.policy_instruction_basis,
                "policy_style": self.policy_style,
                "scan_fields": list(self.scan_fields),
                "policy_kind": self.policy_kind,
                "action_match_mode": self.action_match_mode,
                "field_match_bases": field_match_bases,
            }

            with open(self.output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {"total_hits": self._count, "per_pattern_hits": dict(self._hits)}
