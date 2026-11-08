"""Command line entry point: `manipur <stage> --area <name>`."""

import argparse
from collections.abc import Callable

from manipur.areas import Area, get_area


def run_fetch(area: Area) -> None:
    from manipur.fetch import fetch

    fetch(area)


def run_plan(area: Area) -> None:
    from manipur.plan import plan

    plan(area)


STAGES: dict[str, Callable[[Area], None]] = {
    "fetch": run_fetch,
    "plan": run_plan,
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="manipur")
    commands = parser.add_subparsers(dest="stage", required=True)
    for stage in STAGES:
        commands.add_parser(stage).add_argument("--area", required=True)
    args = parser.parse_args()
    STAGES[args.stage](get_area(args.area))
