import json
import os
import re
import threading
import time
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
    scan_fields: List[str] = field(
        default_factory=lambda: list(_DEFAULT_SCAN_FIELDS)
    )
    policy_kind: str = "resource"

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
        if "action" in self.scan_fields:
            blob["action"] = action
        if "info" in self.scan_fields:
            blob["info"] = info
        if response is not None and "response" in self.scan_fields:
            blob["response"] = response
        if (
            obs
            and isinstance(obs, dict)
            and "a11y_tree" in self.scan_fields
            and "a11y_tree" in obs
        ):
            blob["a11y_tree"] = obs.get("a11y_tree")
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
                "scan_fields": list(self.scan_fields),
                "policy_kind": self.policy_kind,
            }

            with open(self.output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {"total_hits": self._count, "per_pattern_hits": dict(self._hits)}
