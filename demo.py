"""Save a readable, fixed synthetic comparison from the existing simulator."""

from __future__ import annotations

import argparse
from pathlib import Path

from retry_budget_lab import Config, experiment
from retry_budget_report import render_html as render_html
from retry_budget_report import write_report as write_demo

CONFIG = Config(clients=40, base_seconds=0.1, deadline_seconds=0.6)
SEEDS = [0, 1, 2, 3, 4]


def build_report() -> dict:
    return experiment(CONFIG, SEEDS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("demo-output"))
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Choose a new output directory; existing paths are not replaced.")
    report = build_report()
    try:
        write_demo(args.output_dir, report)
    except OSError as error:
        parser.error(f"Cannot save report: {error}. A partial new report directory may remain.")
    capped = report["comparisons"]["capped"]["aggregate"]
    jitter = report["comparisons"]["full-jitter"]["aggregate"]
    print(
        f"capped: {capped['successes']['mean']:.1f} successes, "
        f"{capped['attempts']['mean']:.1f} attempts; "
        f"full jitter: {jitter['successes']['mean']:.1f} successes, "
        f"{jitter['attempts']['mean']:.1f} attempts"
    )
    print(f"Saved {args.output_dir / 'report.html'} and {args.output_dir / 'report.json'}")


if __name__ == "__main__":
    main()
