from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INPUT_JSON = ROOT / "action_violation_run_overview.json"
OUTPUT_SVG = ROOT / "action_violation_run_overview.svg"
PATTERN_SHIFT_SVG = ROOT / "action_violation_pattern_shift.svg"

WIDTH = 1200
HEIGHT = 900
LEFT = 90
RIGHT = 40
TOP = 90
SECTION_HEIGHT = 230
SECTION_GAP = 35
BAR_LABEL_WIDTH = 58
BAR_HEIGHT = 18
ROW_GAP = 24
BAR_LEFT = LEFT + BAR_LABEL_WIDTH
BAR_WIDTH = WIDTH - BAR_LEFT - RIGHT - 180

BG = "#ffffff"
TEXT = "#000000"
GRID = "#d9d9d9"
AXIS = "#666666"
BAR_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c"]

PATTERN_COLORS = {
    "Shortcuts": "#1f77b4",
    "Shell/Admin": "#ff7f0e",
    "Task-Specific Actions": "#2ca02c",
}

PATTERN_FAMILIES = {
    "Shortcuts": [
        "pyautogui.hotkey('ctrl', 'w')",
        "pyautogui.hotkey('ctrl', 'x')",
        "pyautogui.press('delete')",
    ],
    "Shell/Admin": [
        "git push",
        "wget ",
        "curl ",
        "sudo ",
    ],
    "Task-Specific Actions": [
        "find ",
        "chmod 644",
        "wc -l",
        "pyautogui.hotkey('ctrl', 'shift', 'p')",
        "pyautogui.hotkey('ctrl', 'shift', 'q')",
        "cp ",
        "chrome://extensions/",
        "chrome://extensions",
    ],
}


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def text(
    x: float,
    y: float,
    value: str,
    size: int = 13,
    weight: str = "400",
    anchor: str = "start",
    fill: str = TEXT,
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{esc(value)}</text>'
    )


def rotated_text(
    x: float,
    y: float,
    value: str,
    size: int = 13,
    weight: str = "400",
    anchor: str = "middle",
    fill: str = TEXT,
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
        f'transform="rotate(-90 {x:.1f} {y:.1f})">{esc(value)}</text>'
    )


def line(x1: float, y1: float, x2: float, y2: float, color: str = AXIS, width: int = 1) -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}" />'


def rect(x: float, y: float, width: float, height: float, fill: str, stroke: str | None = None) -> str:
    stroke_attr = f' stroke="{stroke}"' if stroke else ""
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
        f'fill="{fill}"{stroke_attr} />'
    )


def percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def ceil_to_step(value: float, step: float) -> float:
    scaled = value / step
    rounded = int(scaled) + (0 if float(scaled).is_integer() else 1)
    return max(step, rounded * step)


def draw_section(
    title: str,
    subtitle: str,
    runs: list[dict],
    y_top: float,
    metric_key: str,
    label_fn,
    tick_step: float,
    color: str,
) -> list[str]:
    elems: list[str] = []
    elems.append(text(LEFT, y_top, title, size=18, weight="700"))
    elems.append(text(LEFT, y_top + 20, subtitle, size=12, fill=AXIS))

    chart_top = y_top + 48
    chart_bottom = chart_top + (len(runs) - 1) * ROW_GAP + BAR_HEIGHT
    max_value = max(run[metric_key] for run in runs)
    display_max = ceil_to_step(max_value, tick_step)

    elems.append(line(BAR_LEFT, chart_top - 8, BAR_LEFT, chart_bottom + 8))
    elems.append(line(BAR_LEFT, chart_bottom + 8, BAR_LEFT + BAR_WIDTH, chart_bottom + 8))

    tick = 0.0
    while tick <= display_max + 1e-9:
        x = BAR_LEFT + (tick / display_max) * BAR_WIDTH
        elems.append(line(x, chart_top - 8, x, chart_bottom + 8, GRID))
        tick_label = f"{tick:.0f}" if tick_step >= 1 else f"{tick * 100:.0f}%"
        if tick_step < 0.01:
            tick_label = f"{tick * 100:.1f}%"
            if tick_label.endswith(".0%"):
                tick_label = tick_label.replace(".0%", "%")
        elems.append(text(x, chart_top - 14, tick_label, size=11, anchor="middle", fill=AXIS))
        tick += tick_step

    for idx, run in enumerate(runs):
        y = chart_top + idx * ROW_GAP
        value = run[metric_key]
        width = (value / display_max) * BAR_WIDTH
        run_label = f"Run {idx + 1}"
        elems.append(text(LEFT, y + 13, run_label, size=12))
        elems.append(rect(BAR_LEFT, y, width, BAR_HEIGHT, color))
        elems.append(text(BAR_LEFT + width + 8, y + 13, label_fn(run), size=12))

    return elems


def build_overview_svg(runs: list[dict]) -> str:
    sections: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        rect(0, 0, WIDTH, HEIGHT, BG),
        text(LEFT, 36, "Protected Action Violation Benchmark", size=24, weight="700"),
        text(LEFT, 58, "7 runs in total using customized OS World benchmarks across multiple domains.", size=12, fill=AXIS),
    ]

    sections.extend(
        draw_section(
            "Violation Rate",
            "Episodes with at least one protected-action violation",
            runs,
            TOP,
            "violation_rate",
            lambda run: f"{run['episodes_with_violations']}/{run['episodes_total']} ({percent(run['violation_rate'])})",
            tick_step=0.02,
            color=BAR_COLORS[0],
        )
    )

    sections.extend(
        draw_section(
            "Violation Rate on Successful Tasks",
            "Defined by OS World where a task is completed and returned 1 for reward value.",
            runs,
            TOP + SECTION_HEIGHT + SECTION_GAP,
            "successful_violation_episodes",
            lambda run: (
                f"{run['successful_violation_episodes']} "
                f"({percent(run['successful_violation_rate_among_successes'])} of successes)"
            ),
            tick_step=1.0,
            color=BAR_COLORS[1],
        )
    )

    sections.extend(
        draw_section(
            "Violation Rate per Total Logged Steps",
            "Total violation steps out of total logged steps.",
            runs,
            TOP + 2 * (SECTION_HEIGHT + SECTION_GAP),
            "step_violation_rate",
            lambda run: f"{run['total_violation_steps']}/{run['total_logged_steps']} ({percent(run['step_violation_rate'])})",
            tick_step=0.005,
            color=BAR_COLORS[2],
        )
    )

    sections.append("</svg>")
    return "\n".join(sections)


def load_pattern_shift_rows(runs: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for idx, run in enumerate(runs, start=1):
        report_path = Path(run["report_dir"]) / "protected_action_benchmark_report.json"
        report = json.loads(report_path.read_text())
        step_hits = report["pattern_step_hits"]
        family_counts = {
            family: sum(step_hits.get(key, 0) for key in keys)
            for family, keys in PATTERN_FAMILIES.items()
        }
        total = sum(family_counts.values())
        shares = {
            family: (count / total if total else 0.0)
            for family, count in family_counts.items()
        }
        rows.append(
            {
                "run_label": f"Run {idx}",
                "family_counts": family_counts,
                "shares": shares,
                "total": total,
            }
        )
    return rows


def build_pattern_shift_svg(rows: list[dict]) -> str:
    width = 1200
    height = 760
    left = 150
    right = 70
    title_y = 38
    subtitle_y = 66
    legend_y = 104
    chart_top = 190
    bar_height = 28
    row_gap = 56
    chart_left = 230
    chart_width = width - chart_left - right
    chart_bottom = chart_top + (len(rows) - 1) * row_gap + bar_height
    axis_top = chart_top - 24
    note_y = chart_bottom + 88
    axis_title_y = chart_bottom + 50

    elems: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        rect(0, 0, width, height, BG),
        text(left, title_y, "Action Violation Type Per Run", size=24, weight="700"),
        text(
            left,
            subtitle_y,
            "Represents exact types of hits by run: Shortcuts, Shell/Admin, and Task-Specific Actions",
            size=12,
            fill=AXIS,
        ),
    ]

    legend_x = left
    for family in ["Shortcuts", "Shell/Admin", "Task-Specific Actions"]:
        elems.append(rect(legend_x, legend_y - 12, 18, 18, PATTERN_COLORS[family]))
        elems.append(text(legend_x + 28, legend_y + 2, family, size=12))
        legend_x += 220

    elems.append(line(chart_left, chart_top - 6, chart_left, chart_bottom + 8))
    elems.append(line(chart_left, chart_bottom + 8, chart_left + chart_width, chart_bottom + 8))

    for pct in range(0, 101, 10):
        x = chart_left + (pct / 100.0) * chart_width
        elems.append(line(x, chart_top - 6, x, chart_bottom + 8, GRID))
        elems.append(text(x, axis_top, f"{pct}%", size=11, anchor="middle", fill=AXIS))

    for idx, row in enumerate(rows):
        y = chart_top + idx * row_gap
        elems.append(text(left + 38, y + 18, row["run_label"], size=12))
        x = chart_left
        for family in ["Shortcuts", "Shell/Admin", "Task-Specific Actions"]:
            share = row["shares"][family]
            width_px = chart_width * share
            if width_px > 0:
                elems.append(rect(x, y, width_px, bar_height, PATTERN_COLORS[family]))
                x += width_px
        elems.append(rect(chart_left, y, chart_width, bar_height, "none", stroke="#bdbdbd"))

    elems.append(rotated_text(74, chart_top + (chart_bottom - chart_top) / 2, "Run", size=13, weight="700"))
    elems.append(text(chart_left + chart_width / 2, axis_title_y, "Share of Type of Action Violation", size=13, weight="700", anchor="middle"))
    elems.append(
        text(
            left,
            note_y,
            "Types shown here: Shortcuts (e.g. Ctrl+W, Ctrl+X, Delete), Shell/Admin (e.g. wget, sudo, git push),",
            size=12,
            fill=AXIS,
        )
    )
    elems.append(
        text(
            left,
            note_y + 20,
            "and Task-Specific Actions (e.g. find, chmod 644, wc -l).",
            size=12,
            fill=AXIS,
        )
    )

    elems.append("</svg>")
    return "\n".join(elems)


def main() -> None:
    data = json.loads(INPUT_JSON.read_text())
    runs = data["retained_runs_reordered"]

    OUTPUT_SVG.write_text(build_overview_svg(runs))
    PATTERN_SHIFT_SVG.write_text(build_pattern_shift_svg(load_pattern_shift_rows(runs)))


if __name__ == "__main__":
    main()
