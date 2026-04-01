import json
import sys
from pathlib import Path


OSWORLD_SRC = Path(__file__).resolve().parents[1] / "src"
if str(OSWORLD_SRC) not in sys.path:
    sys.path.insert(0, str(OSWORLD_SRC))

from doomarena.osworld.lib_run_single import (
    append_episode_error_traj_entry,
    write_terminal_episode_artifacts,
)


def test_terminal_episode_artifacts_write_status_and_result(tmp_path: Path) -> None:
    write_terminal_episode_artifacts(
        example_result_dir=str(tmp_path),
        domain="os",
        example_id="crash-case",
        status="crashed",
        result=0.0,
        error_message="TypeError: boom",
    )

    status_payload = json.loads(
        (tmp_path / "episode_status.json").read_text(encoding="utf-8")
    )
    assert status_payload["status"] == "crashed"
    assert status_payload["result"] == 0.0
    assert status_payload["error"] == "TypeError: boom"
    assert (tmp_path / "result.txt").read_text(encoding="utf-8").strip() == "0.0"


def test_append_episode_error_traj_entry_records_error(tmp_path: Path) -> None:
    append_episode_error_traj_entry(
        example_result_dir=str(tmp_path),
        error_message="RuntimeError: bad state",
        domain="chrome",
        example_id="oops",
    )

    row = json.loads((tmp_path / "traj.jsonl").read_text(encoding="utf-8").strip())
    assert row["Error"] == "RuntimeError: bad state"
    assert row["domain"] == "chrome"
    assert row["example_id"] == "oops"
