"""Run the report scenarios and write results.md.

This is a thin ``--only`` wrapper around ``main.py``, the single producer of
``results.md``: TOP runs on the real scenario fleet. The Clarke-Wright
comparison lives in ``scripts/run_controlled_reports.py``. Kept so existing
``python scripts/run_all.py`` calls (and the scenario-selection tests) keep
working.

Default scenarios: 16, 19, 32, 65 and 69, in that order.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import main as report
from scripts import report_common
from scripts.report_common import add_only_argument, parse_scenario_ids
from utils.scenarios import DEFAULT_REPORT_SCENARIOS

OUT = ROOT / "results.md"
#: Scenarios run by default, in output order.
DEFAULT_SCENARIOS = DEFAULT_REPORT_SCENARIOS


def select_scenarios(
    ids: tuple[str, ...] = DEFAULT_SCENARIOS, root: str | Path = ROOT
) -> list[dict]:
    """The requested scenarios, in the requested order."""
    return report_common.select_scenarios(ids, root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_only_argument(parser, DEFAULT_SCENARIOS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ids = parse_scenario_ids(args.only, DEFAULT_SCENARIOS)
    report.run(ids, OUT)


if __name__ == "__main__":
    main()
