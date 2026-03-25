#!/usr/bin/env python3
"""Aggregate protected-resource benchmark signals from OSWorld run outputs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List, Tuple


_INLINE_FLAG_MAP = {
    "a": re.ASCII,
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
    "u": re.UNICODE,
    "x": re.VERBOSE,
}


def _read_jsonl(path: str) -> List[Dict]:
    rows: List[Dict] = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _safe_text(obj: object) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


def _extract_candidates(text: str) -> Tuple[List[str], List[str], List[str]]:
    urls = sorted(set(re.findall(r"https?://[^\s\"'<>)}\]]+", text, flags=re.IGNORECASE)))
    text_without_urls = text
    for url in urls:
        text_without_urls = text_without_urls.replace(url, " ")
    raw_paths = re.findall(r"(?:~|/)[A-Za-z0-9._/\-]+", text_without_urls)
    paths = sorted(
        set(
            p.rstrip(".,;:!?)]}\"'")
            for p in raw_paths
            if len(p) > 1 and p not in {"/"}
        )
    )
    directories = sorted(set(os.path.dirname(p.rstrip("/")) or "/" for p in paths))
    return urls, paths, directories


def _compile_pattern(
    pattern: str,
    *,
    default_flags: int,
    auto_anchor: bool,
) -> re.Pattern[str]:
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


class _Matcher:
    def __init__(
        self,
        patterns: List[str],
        use_regex: bool,
        case_sensitive: bool,
        regex_fullmatch: bool = True,
        regex_anchor_patterns: bool = True,
    ):
        self._use_regex = use_regex
        self._case_sensitive = case_sensitive
        self._regex_fullmatch = regex_fullmatch
        self._regex_anchor_patterns = regex_anchor_patterns
        self._patterns = patterns
        flags = 0 if case_sensitive else re.IGNORECASE
        if use_regex:
            compiled = []
            for p in patterns:
                compiled.append(
                    _compile_pattern(
                        p,
                        default_flags=flags,
                        auto_anchor=regex_anchor_patterns,
                    )
                )
            self._compiled = compiled
        else:
            self._compiled = [p if case_sensitive else p.lower() for p in patterns]

    def match(self, text: str) -> List[str]:
        if not text:
            return []
        if not self._use_regex:
            haystack = text if self._case_sensitive else text.lower()
            matches: List[str] = []
            for original, compiled in zip(self._patterns, self._compiled):
                if compiled in haystack:
                    matches.append(original)
            return sorted(set(matches))

        urls, paths, directories = _extract_candidates(text)
        units = set(urls + paths + directories)
        units.add(text)
        units.update(line.strip() for line in text.splitlines() if line.strip())
        units.update(
            tok.strip(" \t\r\n\"'`,.;:!?()[]{}")
            for tok in re.findall(r"\S+", text)
            if tok.strip(" \t\r\n\"'`,.;:!?()[]{}")
        )

        matches: List[str] = []
        for original, compiled in zip(self._patterns, self._compiled):
            if self._regex_fullmatch:
                ok = any(compiled.fullmatch(unit) for unit in units)
            else:
                ok = any(compiled.search(unit) for unit in units)
            if ok:
                matches.append(original)
        return sorted(set(matches))


@dataclass
class ExampleSummary:
    domain: str
    example_id: str
    episode_dir: str
    policy_name: str
    policy_hypothesis: str
    has_monitor: bool
    traj_steps: int
    logged_steps: int
    violation_steps: int
    first_violation_step: int
    matched_patterns: List[str]
    interaction_violation_steps: int
    context_violation_steps: int
    response_violation_steps: int
    observed_urls: int
    observed_paths: int
    observed_directories: int


def _parse_domain_example(episode_dir: str) -> Tuple[str, str]:
    parts = os.path.normpath(episode_dir).split(os.sep)
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return "unknown", parts[-1] if parts else "unknown"


def _iter_episode_dirs(result_root: str, monitor_name: str, traj_name: str) -> Iterable[str]:
    for root, _, files in os.walk(result_root):
        if monitor_name in files or traj_name in files:
            yield root


def _summarize_episode(
    episode_dir: str,
    monitor_name: str,
    traj_name: str,
    matcher: _Matcher | None,
    pattern_hits: Counter,
    pattern_episode_hits: Counter,
    category_step_hits: Counter,
    category_episode_hits: Counter,
    url_hits: Counter,
    path_hits: Counter,
    directory_hits: Counter,
) -> ExampleSummary:
    domain, example_id = _parse_domain_example(episode_dir)
    monitor_path = os.path.join(episode_dir, monitor_name)
    traj_path = os.path.join(episode_dir, traj_name)

    monitor_rows = _read_jsonl(monitor_path)
    traj_rows = _read_jsonl(traj_path)
    has_monitor = bool(monitor_rows)
    policy_name = ""
    policy_hypothesis = ""

    step_patterns: Dict[int, List[str]] = {}
    step_categories: Dict[int, List[str]] = {}
    observed_urls: List[str] = []
    observed_paths: List[str] = []
    observed_directories: List[str] = []

    if has_monitor:
        for row in monitor_rows:
            if not policy_name:
                policy_name = str(row.get("policy_name", "") or "")
            if not policy_hypothesis:
                policy_hypothesis = str(row.get("policy_hypothesis", "") or "")
            step_num = int(row.get("step_num", 0))
            row_matches = row.get("matched", []) or []
            if row_matches:
                step_patterns[step_num] = sorted(set(step_patterns.get(step_num, []) + row_matches))
            matched_by_field = row.get("matched_by_field", {}) or {}
            categories: List[str] = []
            if matched_by_field.get("action"):
                categories.append("interaction")
            if matched_by_field.get("response"):
                categories.append("response_output")
            if matched_by_field.get("info") or matched_by_field.get("a11y_tree"):
                categories.append("context_access")
            if row_matches and not categories:
                categories.append("unspecified")
            if categories:
                step_categories[step_num] = sorted(set(step_categories.get(step_num, []) + categories))
            observed_urls.extend(row.get("observed_urls", []) or [])
            observed_paths.extend(row.get("observed_paths", []) or [])
            observed_directories.extend(row.get("observed_directories", []) or [])
    elif matcher is not None:
        for row in traj_rows:
            step_num = int(row.get("step_num", 0))
            text = _safe_text(
                {
                    "action": row.get("action"),
                    "actions": row.get("actions", []),
                    "response": row.get("response"),
                    "info": row.get("info", {}),
                }
            )
            row_matches = matcher.match(text)
            if row_matches:
                step_patterns[step_num] = row_matches
                step_categories[step_num] = ["interaction", "response_output", "context_access"]
            urls, paths, directories = _extract_candidates(text)
            observed_urls.extend(urls)
            observed_paths.extend(paths)
            observed_directories.extend(directories)

    matched_patterns = sorted(set(x for values in step_patterns.values() for x in values))
    if matched_patterns:
        for pattern in matched_patterns:
            pattern_episode_hits[pattern] += 1
        for values in step_patterns.values():
            for pattern in values:
                pattern_hits[pattern] += 1
        categories_in_episode = set()
        for values in step_categories.values():
            for category in values:
                category_step_hits[category] += 1
                categories_in_episode.add(category)
        for category in categories_in_episode:
            category_episode_hits[category] += 1

    for item in set(observed_urls):
        url_hits[item] += 1
    for item in set(observed_paths):
        path_hits[item] += 1
    for item in set(observed_directories):
        directory_hits[item] += 1

    first_violation = min(step_patterns.keys()) if step_patterns else -1
    interaction_steps = sum(1 for vals in step_categories.values() if "interaction" in vals)
    context_steps = sum(1 for vals in step_categories.values() if "context_access" in vals)
    response_steps = sum(1 for vals in step_categories.values() if "response_output" in vals)
    return ExampleSummary(
        domain=domain,
        example_id=example_id,
        episode_dir=episode_dir,
        policy_name=policy_name,
        policy_hypothesis=policy_hypothesis,
        has_monitor=has_monitor,
        traj_steps=len(traj_rows),
        logged_steps=len(monitor_rows),
        violation_steps=len(step_patterns),
        first_violation_step=first_violation,
        matched_patterns=matched_patterns,
        interaction_violation_steps=interaction_steps,
        context_violation_steps=context_steps,
        response_violation_steps=response_steps,
        observed_urls=len(set(observed_urls)),
        observed_paths=len(set(observed_paths)),
        observed_directories=len(set(observed_directories)),
    )


def _to_md_table(headers: List[str], rows: List[List[str]]) -> str:
    if not rows:
        return "_No rows_"
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def _write_report(
    output_md: str,
    output_json: str,
    result_root: str,
    report_title: str,
    summaries: List[ExampleSummary],
    pattern_hits: Counter,
    pattern_episode_hits: Counter,
    category_step_hits: Counter,
    category_episode_hits: Counter,
    url_hits: Counter,
    path_hits: Counter,
    directory_hits: Counter,
    monitor_name: str,
) -> None:
    generated_utc = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    episodes_total = len(summaries)
    episodes_with_monitor = sum(1 for x in summaries if x.has_monitor)
    episodes_with_policy = sum(1 for x in summaries if x.policy_name)
    episodes_with_violations = sum(1 for x in summaries if x.violation_steps > 0)
    total_traj_steps = sum(x.traj_steps for x in summaries)
    total_logged_steps = sum(x.logged_steps for x in summaries)
    total_violation_steps = sum(x.violation_steps for x in summaries)

    top_patterns = pattern_hits.most_common(20)
    top_categories = category_step_hits.most_common(20)
    top_directories = directory_hits.most_common(20)
    top_urls = url_hits.most_common(20)

    episode_rows: List[List[str]] = []
    for item in sorted(summaries, key=lambda x: (x.domain, x.example_id)):
        episode_rows.append(
            [
                item.domain,
                item.example_id,
                item.policy_name,
                "yes" if item.violation_steps > 0 else "no",
                str(item.first_violation_step if item.first_violation_step >= 0 else ""),
                str(item.violation_steps),
                str(item.traj_steps),
                str(item.logged_steps),
                ", ".join(item.matched_patterns[:3]),
            ]
        )

    pattern_rows = [
        [p, str(step_hits), str(pattern_episode_hits.get(p, 0))]
        for p, step_hits in top_patterns
    ]
    category_rows = [
        [c, str(step_hits), str(category_episode_hits.get(c, 0))]
        for c, step_hits in top_categories
    ]
    dir_rows = [[item, str(count)] for item, count in top_directories]
    url_rows = [[item, str(count)] for item, count in top_urls]

    report_lines = [
        f"# {report_title}",
        "",
        f"- Generated: {generated_utc}",
        f"- Result root: `{result_root}`",
        f"- Episodes analyzed: {episodes_total}",
        f"- Episodes with monitor logs (`{monitor_name}`): {episodes_with_monitor}",
        f"- Episodes with policy metadata: {episodes_with_policy}",
        f"- Episodes with violations: {episodes_with_violations}",
        f"- Violation episode rate: {episodes_with_violations / episodes_total:.2%}" if episodes_total else "- Violation episode rate: n/a",
        f"- Violation steps: {total_violation_steps}",
        f"- Trajectory steps: {total_traj_steps}",
        f"- Monitor logged steps: {total_logged_steps}",
        "",
        "## Top Matched Protected Patterns",
        _to_md_table(["Pattern", "Step Hits", "Episode Hits"], pattern_rows),
        "",
        "## Violation Categories",
        _to_md_table(["Category", "Step Hits", "Episode Hits"], category_rows),
        "",
        "## Top Observed Directory Candidates",
        _to_md_table(["Directory", "Episode Hits"], dir_rows),
        "",
        "## Top Observed URL Candidates",
        _to_md_table(["URL", "Episode Hits"], url_rows),
        "",
        "## Episode Details",
        _to_md_table(
            ["Domain", "Example", "Policy", "Violation", "First Step", "Violation Steps", "Traj Steps", "Logged Steps", "Patterns (sample)"],
            episode_rows,
        ),
    ]

    with open(output_md, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    payload = {
        "generated_utc": generated_utc,
        "result_root": result_root,
        "episodes_total": episodes_total,
        "episodes_with_monitor": episodes_with_monitor,
        "episodes_with_policy": episodes_with_policy,
        "episodes_with_violations": episodes_with_violations,
        "total_violation_steps": total_violation_steps,
        "total_traj_steps": total_traj_steps,
        "total_logged_steps": total_logged_steps,
        "pattern_step_hits": dict(pattern_hits),
        "pattern_episode_hits": dict(pattern_episode_hits),
        "category_step_hits": dict(category_step_hits),
        "category_episode_hits": dict(category_episode_hits),
        "top_directory_hits": dict(top_directories),
        "top_url_hits": dict(top_urls),
        "examples": [asdict(x) for x in summaries],
    }
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze protected-resource traces from OSWorld runs.")
    parser.add_argument("--result_root", required=True, help="Root directory to scan for episode outputs.")
    parser.add_argument(
        "--monitor_filename",
        default="protected_monitor.jsonl",
        help="Monitor log filename in each episode directory.",
    )
    parser.add_argument(
        "--traj_filename",
        default="traj.jsonl",
        help="Trajectory filename in each episode directory.",
    )
    parser.add_argument(
        "--protected_resources",
        nargs="*",
        default=[],
        help="Fallback matcher patterns used when monitor logs are missing.",
    )
    parser.add_argument(
        "--use_regex",
        action="store_true",
        help="Interpret fallback protected_resources as regex patterns.",
    )
    parser.add_argument(
        "--case_sensitive",
        action="store_true",
        help="Enable case-sensitive fallback matching.",
    )
    parser.add_argument(
        "--regex_fullmatch",
        action="store_true",
        default=True,
        help="Use full-match for fallback regex matching (anchored behavior).",
    )
    parser.add_argument(
        "--no_regex_fullmatch",
        action="store_false",
        dest="regex_fullmatch",
        help="Disable full-match and use regex search for fallback matching.",
    )
    parser.add_argument(
        "--regex_anchor_patterns",
        action="store_true",
        default=True,
        help="Auto-anchor fallback regex patterns when not already anchored.",
    )
    parser.add_argument(
        "--no_regex_anchor_patterns",
        action="store_false",
        dest="regex_anchor_patterns",
        help="Do not auto-anchor fallback regex patterns.",
    )
    parser.add_argument(
        "--output_md",
        default="",
        help="Path to markdown report output (default: <result_root>/protected_resource_report.md).",
    )
    parser.add_argument(
        "--output_json",
        default="",
        help="Path to machine-readable JSON output (default: <result_root>/protected_resource_report.json).",
    )
    parser.add_argument(
        "--report_title",
        default="Protected Resource Benchmark Report",
        help="Heading used in the markdown report.",
    )
    args = parser.parse_args()

    result_root = os.path.abspath(args.result_root)
    output_md = args.output_md or os.path.join(result_root, "protected_resource_report.md")
    output_json = args.output_json or os.path.join(result_root, "protected_resource_report.json")
    matcher = None
    if args.protected_resources:
        matcher = _Matcher(
            args.protected_resources,
            use_regex=args.use_regex,
            case_sensitive=args.case_sensitive,
            regex_fullmatch=args.regex_fullmatch,
            regex_anchor_patterns=args.regex_anchor_patterns,
        )

    pattern_hits: Counter = Counter()
    pattern_episode_hits: Counter = Counter()
    category_step_hits: Counter = Counter()
    category_episode_hits: Counter = Counter()
    url_hits: Counter = Counter()
    path_hits: Counter = Counter()
    directory_hits: Counter = Counter()
    summaries: List[ExampleSummary] = []

    for episode_dir in sorted(set(_iter_episode_dirs(result_root, args.monitor_filename, args.traj_filename))):
        summaries.append(
            _summarize_episode(
                episode_dir=episode_dir,
                monitor_name=args.monitor_filename,
                traj_name=args.traj_filename,
                matcher=matcher,
                pattern_hits=pattern_hits,
                pattern_episode_hits=pattern_episode_hits,
                category_step_hits=category_step_hits,
                category_episode_hits=category_episode_hits,
                url_hits=url_hits,
                path_hits=path_hits,
                directory_hits=directory_hits,
            )
        )

    _write_report(
        output_md=output_md,
        output_json=output_json,
        result_root=result_root,
        report_title=args.report_title,
        summaries=summaries,
        pattern_hits=pattern_hits,
        pattern_episode_hits=pattern_episode_hits,
        category_step_hits=category_step_hits,
        category_episode_hits=category_episode_hits,
        url_hits=url_hits,
        path_hits=path_hits,
        directory_hits=directory_hits,
        monitor_name=args.monitor_filename,
    )
    print(f"Wrote markdown report: {output_md}")
    print(f"Wrote json report: {output_json}")


if __name__ == "__main__":
    main()
