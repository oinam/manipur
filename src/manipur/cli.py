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


def run_prepare(area: Area) -> None:
    from manipur.prepare import prepare

    prepare(area)


def run_render(area: Area) -> None:
    from manipur.render import render

    render(area)


def run_swatches(area: Area) -> None:
    from manipur.render import swatches

    swatches(area)


def run_detail(area: Area) -> None:
    from manipur.detail import detail

    detail(area)


STAGES: dict[str, Callable[[Area], None]] = {
    "fetch": run_fetch,
    "plan": run_plan,
    "prepare": run_prepare,
    "render": run_render,
    "swatches": run_swatches,
    "detail": run_detail,
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="manipur")
    commands = parser.add_subparsers(dest="stage", required=True)
    for stage in STAGES:
        commands.add_parser(stage).add_argument("--area", required=True)
    args = parser.parse_args()
    STAGES[args.stage](get_area(args.area))
