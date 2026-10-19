# Retry Budget Lab

Compare retry work, completed requests and successful-request latency before
choosing a client retry policy. This local Python simulation sends a synthetic
burst through a finite-capacity FIFO service with an outage and a deadline.
It makes no network calls and does not sleep.

[![Tests](https://github.com/skyon0522-ai/retry-budget-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/skyon0522-ai/retry-budget-lab/actions/workflows/ci.yml)

## Try the comparison

![Actual output from the fixed retry comparison](docs/assets/comparison.png)

The included scenario has 40 requests arriving together, 10 servers, a
0.3-second outage and a 0.6-second deadline. It runs capped exponential
backoff and full jitter with the same five seeds (`0,1,2,3,4`). Python 3.10 or
later is required; no packages, account or external service are needed. From
the repository root:

```sh
python3 demo.py --output-dir demo-output
```

Open `demo-output/report.html` locally. The command also saves the complete
`report.json` with configuration, each seeded run and aggregates. It refuses an
existing output directory. You can inspect the committed [offline HTML](examples/reports/report.html)
and [JSON](examples/reports/report.json) without running Python.

| Policy | Mean completed / 40 | Mean misses | Mean attempts | Mean retries | Pooled successful p99 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Capped backoff | 40.0 | 0.0 | 120.0 | 80.0 | 0.420 s |
| Full jitter | 32.0 | 8.0 | 151.4 | 111.4 | 0.594 s |

These are observed model outputs averaged across five seeded runs; p99 pools
**only successful** request latencies. In this fixed outage, full jitter admits
retries earlier, makes more attempts, yet finishes fewer requests before the
deadline. This is a counterexample to judging a retry policy by timing or
latency alone. It does not show that capped backoff is better in general.

## Read and adapt the experiment

| Start here | Purpose |
| --- | --- |
| [demo.py](demo.py) | Fixed comparison, offline HTML and JSON exports |
| [retry_budget_lab.py](retry_budget_lab.py) | Configuration, event loop, aggregation and command-line interface |
| [METHODOLOGY.md](METHODOLOGY.md) | Event ordering, metric definitions and limits |
| [VALIDATION.md](VALIDATION.md) | Recorded Linux installation, tests and report checks |
| [tests](tests/) | Exact behavior, accounting and example-output checks |
| [Other recorded scenarios](examples/) | Default and shared-budget outputs as well as this short-deadline result |

The demo calls the same `experiment()` function as the CLI. To run another
configuration with the same seeds, use:

```sh
python3 -m retry_budget_lab --clients 40 --base-seconds 0.1 --deadline-seconds 0.6 --seeds 0,1,2,3,4 --report-dir short-deadline-report
python3 -m retry_budget_lab --retry-budget 50 --report-dir budget-50-report
```

Open `report.html` in each new directory. The report shows the actual settings,
both policies and every seeded run; the paired JSON retains all metrics. There
is no web server, JavaScript, account or network request. Use a new directory for
each comparison: an existing file, directory or symbolic link is refused before
the simulation runs. An I/O failure can leave a partial new directory; inspect
it and choose a new path before repeating the command.

`--report-dir` and `--output` are mutually exclusive. Omit both for JSON on stdout,
or use `--output run.json` for JSON only. The latter can replace an existing file;
use a new filename when comparing runs. A completed simulation returns exit code
0 even when requests miss their deadline. Invalid input and report I/O errors
return 2; inspect the metrics to assess a policy. Run
`python3 -m retry_budget_lab --help` for every parameter.

## Install on Linux

Python 3.10 or later and its `venv` support are required. Clone the repository,
then create an isolated environment. The runtime has no third-party dependencies;
pip may download setuptools while building the package.

```sh
git clone https://github.com/skyon0522-ai/retry-budget-lab.git
cd retry-budget-lab
python3 -m venv .venv
.venv/bin/python -m pip install .
project_dir="$PWD"
run_dir="$(mktemp -d)"
cd "$run_dir"
"$project_dir/.venv/bin/retry-budget-lab" --clients 40 --base-seconds 0.1 --deadline-seconds 0.6 --report-dir comparison
```

Open `comparison/report.html` from the printed path in a browser. On a machine
without a graphical browser, copy the directory to one with a browser; keep
`report.json` beside the HTML. The command works outside the source checkout.
The fixed `demo.py` remains a source-only shortcut for the example above.

The [default case](examples/default.json) completes 200/200 requests under
both policies. The [shared-cap case](examples/budget-50.json) admits fewer
retries but leaves 100/200 requests unsuccessful under both policies. Its
lower successful p99 must be read with those misses. The short-deadline case
above makes the timing tradeoff visible. The model never changes a deployed
client or service.

## What the numbers mean

All requests arrive at time zero. Each attempt occupies one server for a
fixed duration; attempts started during the outage fail after using that
capacity. Excess attempts wait in a FIFO queue. An end-to-end deadline covers
backoff, queueing and service. A completion exactly at the deadline misses.
Running work can continue after its caller expires.

`attempts` counts first attempts and admitted retries; `retry_attempts` counts
only retries. The optional `retry_budget` is a fixed, run-wide admission cap,
not an adaptive token bucket. Capped backoff waits for its capped exponential
window; full jitter draws a seeded delay between zero and that window. The
simulator records completed requests and all three miss reasons separately.
See [METHODOLOGY.md](METHODOLOGY.md) for the event path, accounting equations
and exact percentile definition.

This model uses one simultaneous burst, identical service times, constant
capacity, one outage and an unbounded waiting room. It does not model network
delay, changing arrivals, partial success, overlapping retries, provider
rate limits, token costs or real workload traces. No checked-in scenario was
calibrated to a customer or provider. Validate the assumptions with measured
traffic, downstream limits and idempotency requirements before making an
operational decision. The research context is in [references.bib](references.bib);
it does not validate these numerical results.

## Development

Run these commands from the repository root, using the environment created above.

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip install ruff==0.16.10
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

The tests cover exact FIFO and deadline behavior, retry budgets, repeatability,
input rejection, conservation across 90 scenarios and the committed demo
outputs. Report checks cover custom settings, absent successful percentiles,
preserved existing output and partial I/O failure. The
[GitHub CI run](https://github.com/skyon0522-ai/retry-budget-lab/actions/runs/38686785815)
succeeded on Python 3.10, 3.12 and 3.14 at
[commit `3a766d4`](https://github.com/skyon0522-ai/retry-budget-lab/commit/3a766d46eec0912582cd5290fe397abc8d3da4dd),
including installed report output outside the checkout. Results checked on
2026-10-18. The scoped local evidence is in [VALIDATION.md](VALIDATION.md).
Local code is [MIT-licensed](LICENSE).
