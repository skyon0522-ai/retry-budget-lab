"""Save a readable, fixed synthetic comparison from the existing simulator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from retry_budget_lab import Config, experiment

CONFIG = Config(clients=40, base_seconds=0.1, deadline_seconds=0.6)
SEEDS = [0, 1, 2, 3, 4]


def build_report() -> dict:
    return experiment(CONFIG, SEEDS)


def render_html(report: dict) -> str:
    rows = []
    for key, name in (("capped", "Capped backoff"), ("full-jitter", "Full jitter")):
        policy = report["comparisons"][key]
        metrics = policy["aggregate"]
        latency = policy["pooled_success_latency_seconds"]["p99"]
        rows.append(
            "<tr><th scope='row'>"
            + name
            + "</th><td>"
            + f"{metrics['successes']['mean']:.1f} / {report['config']['clients']}"
            + "</td><td>"
            + f"{metrics['misses']['mean']:.1f}"
            + "</td><td>"
            + f"{metrics['attempts']['mean']:.1f}"
            + "</td><td>"
            + f"{metrics['retry_attempts']['mean']:.1f}"
            + "</td><td>"
            + (f"{latency:.3f} s" if latency is not None else "No successes")
            + "</td></tr>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Retry policy comparison</title>
<style>
body{{font:16px/1.55 system-ui,sans-serif;margin:0;background:#f4f7fb;color:#182736}}
main{{max-width:70rem;margin:auto;padding:2rem 1rem}}h1{{line-height:1.2}}
p{{max-width:75ch}}
.panel{{background:white;border:1px solid #d1dce8;border-radius:.6rem}}
.panel{{padding:1.5rem;margin:1.2rem 0}}
.scroll{{overflow:auto;max-width:100%}}
.scroll:focus-visible,a:focus-visible{{outline:3px solid #155b87;outline-offset:2px}}
table{{border-collapse:collapse;width:100%;min-width:43rem}}
th,td{{text-align:left;padding:.7rem;border-bottom:1px solid #d1dce8}}
thead{{background:#eaf1f8}}code{{overflow-wrap:anywhere}}a{{color:#155b87}}
@media(max-width:600px){{main{{padding:1rem .5rem}}.panel{{padding:1rem}}}}
@media print{{body{{background:white}}main{{max-width:none;padding:0}}.panel{{border:0;padding:0}}}}
</style></head><body><main>
<h1>Retry budget comparison</h1>
<p>Forty simulated requests arrive together. Ten servers take 0.02 seconds per attempt;
an attempt started before 0.3 seconds fails, and each request has a 0.6-second deadline.
Both policies use the same five seeds (0–4).</p>
<section class="panel"><h2>Observed model output</h2>
<div class="scroll" role="region" aria-label="Retry policy comparison table" tabindex="0"><table>
<thead><tr><th scope="col">Policy</th><th scope="col">Mean completed</th>
<th scope="col">Mean missed</th><th scope="col">Mean attempts</th>
<th scope="col">Mean retries</th><th scope="col">Pooled successful p99</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<p>Full jitter admits retries earlier in this outage. It makes more attempts yet finishes
fewer requests before the deadline. The p99 pools successful requests across the five
seeds; read it with the missed-request count.</p>
<p><a href="report.json">Inspect the full configuration, five individual runs and
aggregate JSON</a>.</p></section>
<section class="panel"><h2>What this means</h2>
<p>This fixed FIFO/outage model shows why retry timing, downstream work and missed
deadlines must be considered together. It makes no network calls. It is not calibrated
to a customer or provider and does not establish a generally superior retry policy
or production SLO.</p>
</section></main></body></html>
"""


def write_demo(output: Path, report: dict) -> None:
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output / "report.html").write_text(render_html(report), encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("demo-output"))
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("Choose a new output directory; existing paths are not replaced.")
    report = build_report()
    write_demo(args.output_dir, report)
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
