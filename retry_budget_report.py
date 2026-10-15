"""Offline views of existing experiment results; no simulation or network I/O."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path


def render_html(report: dict) -> str:
    config = report["config"]
    rows, runs = [], []
    for key, name in (("capped", "Capped backoff"), ("full-jitter", "Full jitter")):
        policy = report["comparisons"][key]
        metrics = policy["aggregate"]
        latency = policy["pooled_success_latency_seconds"]["p99"]
        rows.append(
            "<tr><th scope='row'>"
            + name
            + "</th><td>"
            + f"{metrics['successes']['mean']:.1f} / {config['clients']}"
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
        for run in policy["runs"]:
            p99 = run["success_latency_seconds"]["p99"]
            cells = [name, run["seed"], run["successes"], run["misses"], run["attempts"]]
            cells += [run["retry_attempts"], f"{p99:.3f} s" if p99 is not None else "No successes"]
            runs.append("<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in cells) + "</tr>")

    settings = []
    for key, label in (
        ("clients", "Requests"),
        ("servers", "Servers"),
        ("service_seconds", "Service seconds per attempt"),
        ("outage_seconds", "Outage seconds"),
        ("deadline_seconds", "Deadline seconds"),
        ("max_attempts", "Maximum attempts per request"),
        ("base_seconds", "Initial backoff seconds"),
        ("cap_seconds", "Backoff cap seconds"),
        ("retry_budget", "Shared retry admission cap"),
    ):
        value = config[key]
        display = "Unlimited" if value is None else str(value)
        settings.append(f"<tr><th scope='row'>{label}</th><td>{escape(display)}</td></tr>")
    seeds = escape(", ".join(str(seed) for seed in report["seeds"]))
    headings = "".join(
        f"<th scope='col'>{label}</th>"
        for label in (
            "Policy",
            "Seed",
            "Completed",
            "Missed",
            "Attempts",
            "Retries",
            "Successful p99",
        )
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>Retry policy comparison</title>
<style>
body{{font:16px/1.55 system-ui,sans-serif;margin:0;background:#f4f7fb;color:#182736}}
main{{max-width:70rem;margin:auto;padding:2rem 1rem}}h1{{line-height:1.2}}
p{{max-width:75ch}}
.panel{{background:white;border:1px solid #d1dce8;border-radius:.6rem}}
.panel{{padding:1.5rem;margin:1.2rem 0}}
.scroll{{overflow:auto;max-width:100%}}
.scroll:focus-visible,a:focus-visible,summary:focus-visible{{
outline:3px solid #155b87;outline-offset:2px}}
table{{border-collapse:collapse;width:100%;min-width:43rem}}
th,td{{text-align:left;padding:.7rem;border-bottom:1px solid #d1dce8}}
thead{{background:#eaf1f8}}code{{overflow-wrap:anywhere}}a{{color:#155b87}}
summary{{cursor:pointer;font-weight:600}}.settings{{min-width:0}}
@media(max-width:600px){{main{{padding:1rem .5rem}}.panel{{padding:1rem}}}}
@media print{{body{{background:white}}main{{max-width:none;padding:0}}.panel{{border:0;padding:0}}}}
</style></head><body><main>
<h1>Retry budget comparison</h1>
<p>Simulated requests: {escape(str(config["clients"]))}, all arriving at time zero.
Server count: {escape(str(config["servers"]))}; service time:
{escape(str(config["service_seconds"]))} seconds per attempt.
An attempt started before {escape(str(config["outage_seconds"]))}
seconds fails; each request has a {escape(str(config["deadline_seconds"]))}-second deadline.
Seeds for both policies: <code>{seeds}</code>.</p>
<section class="panel"><h2>Observed model output</h2>
<div class="scroll" role="region" aria-label="Retry policy comparison table" tabindex="0"><table>
<thead><tr><th scope="col">Policy</th><th scope="col">Mean completed</th>
<th scope="col">Mean missed</th><th scope="col">Mean attempts</th>
<th scope="col">Mean retries</th><th scope="col">Pooled successful p99</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<p>On small screens, swipe the table sideways or focus it and use the arrow keys
to read all columns.</p>
<p>Read completed requests, misses and admitted attempts together. The p99 pools
only successful request latencies across seeds; it excludes every missed request.
No successes means there is no successful-request percentile, not zero latency.</p>
<p><a href="report.json">Inspect the full configuration, individual runs and aggregate JSON</a>.</p>
</section>
<details class="panel"><summary>Configuration and seeds</summary>
<table class="settings"><caption>Settings used for this run</caption>
<tbody>{"".join(settings)}</tbody></table>
<p>Seeds: <code>{seeds}</code>. Each seed has equal request counts.
Capped backoff is deterministic; different seeds do not change its result.</p></details>
<details class="panel"><summary>Individual seeded runs</summary>
<div class="scroll" role="region" aria-label="Individual seeded runs table" tabindex="0"><table>
<thead><tr>{headings}</tr></thead>
<tbody>{"".join(runs)}</tbody></table></div>
<p>These are observed runs, not confidence intervals. The pooled p99 above is not
the average of the per-run p99 values.</p></details>
<section class="panel"><h2>What this means</h2>
<p>This FIFO/outage model shows why retry timing, downstream work and missed
deadlines must be considered together. A completion exactly at the deadline misses.
It makes no network calls. It is not calibrated to a customer or provider and does
not establish a generally superior retry policy or production SLO.</p>
</section></main></body></html>
"""


def write_report(output: Path, report: dict) -> None:
    """Create a new report directory. An I/O failure may leave partial output."""
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output / "report.html").write_text(render_html(report), encoding="utf-8", newline="\n")
