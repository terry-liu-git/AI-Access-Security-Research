#!/usr/bin/env python3
"""Build a full OSWorld manifest excluding tasks that require Google Drive auth."""

from __future__ import annotations

import argparse
import json
import os
from collections import OrderedDict
from typing import Dict, List


def _requires_gdrive_auth(example: Dict) -> bool:
    for cfg in example.get("config", []):
        cfg_type = cfg.get("type")
        params = cfg.get("parameters", {}) or {}
        if cfg_type == "googledrive":
            return True
        if cfg_type == "login" and params.get("platform") == "googledrive":
            return True
    return False


def build_manifest(base_dir: str) -> Dict[str, List[str]]:
    test_all_path = os.path.join(base_dir, "test_all.json")
    with open(test_all_path, "r", encoding="utf-8") as f:
        full_manifest = json.load(f)

    filtered: Dict[str, List[str]] = OrderedDict()
    for domain in sorted(full_manifest.keys()):
        kept: List[str] = []
        for example_id in full_manifest[domain]:
            example_path = os.path.join(base_dir, "examples", domain, f"{example_id}.json")
            with open(example_path, "r", encoding="utf-8") as ef:
                example = json.load(ef)
            if not _requires_gdrive_auth(example):
                kept.append(example_id)
        filtered[domain] = kept
    return filtered


def main() -> None:
    parser = argparse.ArgumentParser(description="Build OSWorld full manifest excluding Google Drive auth tasks.")
    parser.add_argument(
        "--evaluation_examples_dir",
        default="../OSWorld/evaluation_examples",
        help="Path to OSWorld evaluation_examples directory.",
    )
    parser.add_argument(
        "--output",
        default="doomarena/osworld/src/doomarena/osworld/scripts/test_all_no_gdrive.json",
        help="Output path for generated manifest JSON.",
    )
    args = parser.parse_args()

    manifest = build_manifest(os.path.abspath(args.evaluation_examples_dir))
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in manifest.values())
    print(f"Wrote {args.output} with {total} examples.")
    for domain, ids in manifest.items():
        print(f"{domain}: {len(ids)}")


if __name__ == "__main__":
    main()
