#!/usr/bin/env python3
"""Re-verify protected-resource violations against raw trajectory artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from doomarena.osworld.protected_monitor import (
    _RESOURCE_URL_RE,
    _compile_pattern,
    _normalize_observed_path,
    _normalize_observed_url,
    _safe_to_text,
    canonicalize_action_for_matching,
)


_TOKEN_STRIP = " \t\r\n\"'`,.;:!?()[]{}"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _extract_units(text: str) -> List[str]:
    if not text:
        return []

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
        {
            normalized
            for path in raw_paths
            if (normalized := _normalize_observed_path(path))
            and len(normalized) > 1
            and normalized not in {"/"}
        }
    )
    directories = sorted(
        {
            _normalize_observed_path(os.path.dirname(path.rstrip("/")) or "/")
            for path in paths
        }
    )

    units = set(urls + paths + directories)
    units.add(text)
    units.update(line.strip() for line in text.splitlines() if line.strip())
    units.update(
        token.strip(_TOKEN_STRIP)
        for token in re.findall(r"\S+", text)
        if token.strip(_TOKEN_STRIP)
    )
    return sorted(unit for unit in units if unit)


def _make_snippet(text: str, needle: str, radius: int = 80) -> str:
    if not text or not needle:
        return ""
    idx = text.find(needle)
    if idx < 0:
        return ""
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end] + suffix


def _verify_literal(text: str, literal: str, case_sensitive: bool) -> List[Dict[str, str]]:
    if not text or not literal:
        return []

    haystack = text if case_sensitive else text.lower()
    needle = literal if case_sensitive else literal.lower()
    idx = haystack.find(needle)
    if idx < 0:
        return []

    matched_value = text[idx : idx + len(literal)]
    return [
        {
            "match_kind": "literal_substring",
            "matched_value": matched_value,
            "snippet": _make_snippet(text, matched_value),
        }
    ]


def _verify_regex(
    text: str,
    pattern: str,
    *,
    case_sensitive: bool,
    regex_fullmatch: bool,
    regex_anchor_patterns: bool,
    max_evidence: int = 5,
) -> List[Dict[str, str]]:
    if not text or not pattern:
        return []

    flags = 0 if case_sensitive else re.IGNORECASE
    compiled = _compile_pattern(
        pattern,
        default_flags=flags,
        auto_anchor=regex_anchor_patterns,
    )

    evidence: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for unit in _extract_units(text):
        match = compiled.fullmatch(unit) if regex_fullmatch else compiled.search(unit)
        if not match:
            continue
        matched_value = match.group(0)
        dedupe_key = (unit, matched_value)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        evidence.append(
            {
                "match_kind": "regex_fullmatch" if regex_fullmatch else "regex_search",
                "unit": unit,
                "matched_value": matched_value,
                "snippet": _make_snippet(text, matched_value) or unit,
            }
        )
        if len(evidence) >= max_evidence:
            break
    return evidence


def _episode_identity(episode_dir: Path) -> Tuple[str, str]:
    parts = episode_dir.parts
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return "unknown", episode_dir.name


def _iter_episode_dirs(result_root: Path, monitor_name: str, traj_name: str) -> Iterable[Path]:
    for root, _, files in os.walk(result_root):
        file_set = set(files)
        if monitor_name in file_set or traj_name in file_set:
            yield Path(root)


def _verify_episode(
    episode_dir: Path,
    *,
    monitor_name: str,
    traj_name: str,
    case_sensitive: bool,
    regex_fullmatch: bool,
    regex_anchor_patterns: bool,
) -> List[Dict[str, Any]]:
    monitor_rows = _read_jsonl(episode_dir / monitor_name)
    if not monitor_rows:
        return []

    flagged_rows = [row for row in monitor_rows if row.get("matched")]
    if not flagged_rows:
        return []

    traj_rows = _read_jsonl(episode_dir / traj_name)
    traj_by_step = {
        int(row.get("step_num", 0)): row for row in traj_rows if int(row.get("step_num", 0)) > 0
    }

    domain, example_id = _episode_identity(episode_dir)
    verified_rows: List[Dict[str, Any]] = []
    for row in flagged_rows:
        step_num = int(row.get("step_num", 0))
        traj_row = traj_by_step.get(step_num, {})

        action_value = traj_row.get("actions", [])
        if str(row.get("policy_kind", "")) == "action":
            action_value = canonicalize_action_for_matching(action_value)

        # `ProtectedResourceMonitor.observe_step()` logs the list of actions under field `action`.
        field_values: Dict[str, Any] = {
            "action": action_value,
            "response": traj_row.get("response"),
            "info": traj_row.get("info", {}),
        }
        field_text = {name: _safe_to_text(value) for name, value in field_values.items()}

        policy_literals = list(row.get("policy_literals", []) or [])
        policy_regex = list(row.get("policy_regex", []) or [])

        verified_by_field: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
        for field_name, text in field_text.items():
            field_evidence: Dict[str, List[Dict[str, str]]] = {}
            for literal in policy_literals:
                evidence = _verify_literal(text, literal, case_sensitive=case_sensitive)
                if evidence:
                    field_evidence[literal] = evidence
            for pattern in policy_regex:
                evidence = _verify_regex(
                    text,
                    pattern,
                    case_sensitive=case_sensitive,
                    regex_fullmatch=regex_fullmatch,
                    regex_anchor_patterns=regex_anchor_patterns,
                )
                if evidence:
                    field_evidence[pattern] = evidence
            if field_evidence:
                verified_by_field[field_name] = field_evidence

        reported_by_field = row.get("matched_by_field", {}) or {}
        reported_patterns = list(row.get("matched", []) or [])

        confirmed_pairs: List[Dict[str, str]] = []
        misplaced_pairs: List[Dict[str, Any]] = []
        missing_pairs: List[Dict[str, str]] = []
        unavailable_pairs: List[Dict[str, str]] = []

        if reported_by_field:
            for field_name, patterns in reported_by_field.items():
                for pattern in patterns:
                    if field_name not in field_text:
                        unavailable_pairs.append({"field": field_name, "pattern": pattern})
                        continue
                    if pattern in verified_by_field.get(field_name, {}):
                        confirmed_pairs.append({"field": field_name, "pattern": pattern})
                        continue
                    found_elsewhere = [
                        name
                        for name, pattern_map in verified_by_field.items()
                        if pattern in pattern_map
                    ]
                    if found_elsewhere:
                        misplaced_pairs.append(
                            {"field": field_name, "pattern": pattern, "found_in": found_elsewhere}
                        )
                    else:
                        missing_pairs.append({"field": field_name, "pattern": pattern})
        else:
            for pattern in reported_patterns:
                found_fields = [
                    name for name, pattern_map in verified_by_field.items() if pattern in pattern_map
                ]
                if found_fields:
                    confirmed_pairs.extend(
                        {"field": field_name, "pattern": pattern} for field_name in found_fields
                    )
                else:
                    missing_pairs.append({"field": "unknown", "pattern": pattern})

        if missing_pairs:
            status = "unconfirmed"
        elif unavailable_pairs or misplaced_pairs:
            status = "needs_review"
        else:
            status = "confirmed"

        evidence_view = {
            field_name: {
                pattern: pattern_evidence
                for pattern, pattern_evidence in pattern_map.items()
                if pattern in set(reported_patterns)
            }
            for field_name, pattern_map in verified_by_field.items()
        }
        evidence_view = {k: v for k, v in evidence_view.items() if v}

        verified_rows.append(
            {
                "domain": domain,
                "example_id": example_id,
                "episode_dir": str(episode_dir),
                "step_num": step_num,
                "status": status,
                "reported_patterns": reported_patterns,
                "reported_by_field": reported_by_field,
                "confirmed_pairs": confirmed_pairs,
                "misplaced_pairs": misplaced_pairs,
                "missing_pairs": missing_pairs,
                "unavailable_pairs": unavailable_pairs,
                "verified_evidence": evidence_view,
                "policy_non_protected_examples": list(
                    row.get("policy_non_protected_examples", []) or []
                ),
                "notes": [
                    (
                        "Verification uses canonical executable action text for "
                        "action-policy rows and raw `traj.jsonl` fields for "
                        "`response`/`info`."
                    ),
                    "If a hit was only logged in `a11y_tree`, it cannot be fully re-verified after the run because that field is not stored in `traj.jsonl`.",
                ],
            }
        )

    return verified_rows


def _write_md(output_path: Path, report: Dict[str, Any]) -> None:
    lines = [
        "# Protected Violation Verification Report",
        "",
        f"- Generated: {report['generated_utc']}",
        f"- Result root: `{report['result_root']}`",
        f"- Flagged violation rows: `{report['flagged_rows']}`",
        f"- Confirmed rows: `{report['confirmed_rows']}`",
        f"- Needs review rows: `{report['needs_review_rows']}`",
        f"- Unconfirmed rows: `{report['unconfirmed_rows']}`",
        "",
    ]

    if not report["rows"]:
        lines.append("_No flagged violation rows found._")
    else:
        lines.extend(
            [
                "| Domain | Example | Step | Status | Reported Patterns |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in report["rows"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        row["domain"],
                        row["example_id"],
                        str(row["step_num"]),
                        row["status"],
                        ", ".join(row["reported_patterns"]),
                    ]
                )
                + " |"
            )
        lines.append("")
        for row in report["rows"]:
            lines.append(
                f"## {row['domain']}/{row['example_id']} step {row['step_num']} ({row['status']})"
            )
            lines.append("")
            lines.append(f"- Episode dir: `{row['episode_dir']}`")
            if row["missing_pairs"]:
                lines.append(f"- Missing pairs: `{json.dumps(row['missing_pairs'])}`")
            if row["misplaced_pairs"]:
                lines.append(f"- Misplaced pairs: `{json.dumps(row['misplaced_pairs'])}`")
            if row["unavailable_pairs"]:
                lines.append(f"- Unavailable pairs: `{json.dumps(row['unavailable_pairs'])}`")
            if row["verified_evidence"]:
                lines.append("- Verified evidence:")
                for field_name, field_map in row["verified_evidence"].items():
                    lines.append(f"  - `{field_name}`")
                    for pattern, evidence in field_map.items():
                        lines.append(f"    - `{pattern}`")
                        for item in evidence:
                            snippet = item.get("snippet", "").replace("\n", "\\n")
                            lines.append(
                                f"      - `{item.get('matched_value', '')}` | `{snippet}`"
                            )
            lines.append("")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Double-check protected-resource violations against raw trajectory logs."
    )
    parser.add_argument("--result-root", required=True, help="Run result root to scan.")
    parser.add_argument(
        "--monitor-name",
        default="protected_monitor.jsonl",
        help="Monitor filename inside each episode directory.",
    )
    parser.add_argument(
        "--traj-name",
        default="traj.jsonl",
        help="Trajectory filename inside each episode directory.",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Use case-sensitive matching when re-checking patterns.",
    )
    parser.add_argument(
        "--regex-search",
        action="store_true",
        help="Use regex search instead of fullmatch on extracted units.",
    )
    parser.add_argument(
        "--no-regex-anchor-patterns",
        action="store_true",
        help="Disable automatic ^...$ anchoring for regex verification.",
    )
    parser.add_argument("--output-json", help="Optional JSON output path.")
    parser.add_argument("--output-md", help="Optional Markdown output path.")
    args = parser.parse_args()

    result_root = Path(args.result_root)
    rows: List[Dict[str, Any]] = []
    for episode_dir in sorted(
        _iter_episode_dirs(result_root, args.monitor_name, args.traj_name)
    ):
        rows.extend(
            _verify_episode(
                episode_dir,
                monitor_name=args.monitor_name,
                traj_name=args.traj_name,
                case_sensitive=args.case_sensitive,
                regex_fullmatch=not args.regex_search,
                regex_anchor_patterns=not args.no_regex_anchor_patterns,
            )
        )

    confirmed_rows = sum(1 for row in rows if row["status"] == "confirmed")
    needs_review_rows = sum(1 for row in rows if row["status"] == "needs_review")
    unconfirmed_rows = sum(1 for row in rows if row["status"] == "unconfirmed")
    report = {
        "generated_utc": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "result_root": str(result_root),
        "flagged_rows": len(rows),
        "confirmed_rows": confirmed_rows,
        "needs_review_rows": needs_review_rows,
        "unconfirmed_rows": unconfirmed_rows,
        "rows": rows,
    }

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.output_md:
        _write_md(Path(args.output_md), report)

    print(
        json.dumps(
            {
                "result_root": report["result_root"],
                "flagged_rows": report["flagged_rows"],
                "confirmed_rows": report["confirmed_rows"],
                "needs_review_rows": report["needs_review_rows"],
                "unconfirmed_rows": report["unconfirmed_rows"],
            },
            ensure_ascii=False,
        )
    )
    for row in rows:
        print(
            json.dumps(
                {
                    "domain": row["domain"],
                    "example_id": row["example_id"],
                    "step_num": row["step_num"],
                    "status": row["status"],
                    "reported_patterns": row["reported_patterns"],
                    "reported_by_field": row["reported_by_field"],
                    "verified_evidence": row["verified_evidence"],
                    "missing_pairs": row["missing_pairs"],
                    "misplaced_pairs": row["misplaced_pairs"],
                    "unavailable_pairs": row["unavailable_pairs"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
