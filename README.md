# Retry Budget Lab

Measure the work, completion rate, and tail latency of retry policies before choosing a retry budget for an AI or cloud client.

This small, standard-library Python experiment sends a simulated burst through a **finite-capacity FIFO service**, with an outage, an end-to-end deadline, a per-request attempt limit, and an optional shared retry cap. It compares capped exponential backoff with full jitter. It makes no network calls and does not sleep.

## Run an experiment

Python 3.10 or later; no runtime dependencies or installation required:

```sh
python -m retry_budget_lab --output results.json
python -m unittest discover -s tests -v
```

Optional installation adds a command:

```sh
python -m pip install .
retry-budget-lab --clients 40 --base-seconds 0.1 --deadline-seconds 0.6 --seeds 0,1,2,3,4
```

Every result includes its complete configuration, seeds, individual runs, and aggregate metrics. Times are in seconds. The default seeds are `0,1,2,3,4`; supply a different, explicit list for sensitivity analysis. `--max-attempts 1` disables retries. `--retry-budget 0` also admits no retries, while reporting budget exhaustion separately from an attempt limit.

## Observed examples

These outputs were generated locally with Python 3.12.3. Each row averages five runs; p99 is the nearest-rank percentile of **pooled successful requests only**. Failure counts must be read alongside latency. Full machine-readable results are checked in under [`examples/`](examples/).

| Scenario | Policy | Successes / requests | Attempts | Amplification | Successful p99 | Misses |
|---|---|---:|---:|---:|---:|---:|
| Default, queue stays busy | Capped | 200 / 200 | 350 | 1.750 | 0.700 s | 0 |
| Default, queue stays busy | Full jitter | 200 / 200 | 350 | 1.750 | 0.700 s | 0 |
| Shared retry budget 50 | Capped | 100 / 200 | 250 | 1.250 | 0.500 s | 100 |
| Shared retry budget 50 | Full jitter | 100 / 200 | 250 | 1.250 | 0.500 s | 100 |
| 40 requests, 0.6 s deadline | Capped | 40 / 40 | 120 | 3.000 | 0.420 s | 0 |
| 40 requests, 0.6 s deadline | Full jitter | 32 / 40 | 151.4 | 3.785 | 0.594 s | 8 |

The default queue absorbs the different retry timings, so the policies have identical totals. The shared cap admits less work but leaves half the requests unsuccessful; its lower successful p99 is not an overall improvement. In the smaller burst, full jitter retries sooner during the outage. Across these five seeds, it completes 31–33 requests, with mean 7.4 deadline misses and 0.6 attempt-limit misses. These outcomes are consequences of this service model, not a ranking of retry policies for every system.

Reproduce the three scenarios:

```sh
python -m retry_budget_lab --output examples/default.json
python -m retry_budget_lab --retry-budget 50 --output examples/budget-50.json
python -m retry_budget_lab --clients 40 --base-seconds 0.1 --deadline-seconds 0.6 --output examples/short-deadline.json
```

All requests arrive together, so peak backlog is the burst size and peak queue is the burst size minus available servers: 200/190 or 40/30 in these examples. This metric does not demonstrate a jitter benefit. The simulator uses individual arrival, completion, and deadline events; it does not infer contention from counts in arbitrary time buckets.

## What the model means

1. All logical requests arrive at time zero. Each admits a first attempt without spending a retry token.
2. At most `servers` attempts run concurrently; each consumes `service_seconds`. Excess attempts wait in an unbounded FIFO queue.
3. An attempt **starting** before `outage_seconds` fails after consuming its full service time. Later starts succeed. Recovery does not rescue an already running failed attempt.
4. After failed attempt number `n`, the backoff window is `min(cap_seconds, base_seconds * 2**(n-1))`. Capped backoff waits for that window; full jitter draws uniformly from zero to the window.
5. A request may have at most one queued or running attempt. `max_attempts` includes the first attempt. An optional `retry_budget` is a fixed, run-wide cap on **admitted retries**, consumed when a retry arrives. It never refills; this is not adaptive throttling or a token bucket.
6. The absolute deadline applies to queueing, service, and backoff together. A completion exactly at the deadline is a miss. Expired queued attempts never start; running attempts continue consuming service capacity until completion.

See [`METHODOLOGY.md`](METHODOLOGY.md) for event ordering, metric definitions, architecture, and limitations.

## References and implementation choices

The experiment is original code; no upstream implementation was copied. Its inputs and checks were informed by these inspected sources:

- [Tenacity `wait.py`](https://github.com/jd/tenacity/blob/58c45dc02b33012be37ea634c81e01ae9ccd05a0/tenacity/wait.py) and [`stop.py`](https://github.com/jd/tenacity/blob/58c45dc02b33012be37ea634c81e01ae9ccd05a0/tenacity/stop.py): separate waiting decisions from attempt and deadline limits. This project does not wrap or replace Tenacity.
- Marc Brooker, [Exponential Backoff And Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/) (2015): capped backoff and full-jitter definitions. The article models optimistic concurrency contention; this repository models a FIFO service, so it does **not** replicate that experiment or its numerical results.
- Alejandro Forero Cuervo, [Handling Overload](https://sre.google/sre-book/handling-overload/): finite resource capacity and client-side traffic control motivate making service work and retry admission explicit. The chapter's adaptive throttling algorithm is not implemented here.
- Jeffrey Dean and Luiz André Barroso, [The Tail at Scale](https://research.google/pubs/the-tail-at-scale/), *Communications of the ACM* 56 (2013), 74–80: motivates reporting tail latency. The paper is scholarly context; its systems and experiments are not reproduced here.

[`references.bib`](references.bib) contains source citations. [`CITATION.cff`](CITATION.cff) identifies this software. References do not imply endorsement.

## Applying this to a client integration

Use measured arrival patterns, service costs, timeout behavior, and downstream limits before drawing operational conclusions. AI integrations also need explicit policies for idempotency, token/cost limits, streaming, and partially completed operations; this experiment does not model those concerns.

## Development

```sh
python -m unittest discover -s tests -v
python -m pip install ruff==0.16.10
ruff check .
ruff format --check .
```

Tests cover exact one-client and FIFO outcomes, outage recovery, deadline ties, non-cancellable work, zero retries, the shared cap, repeatability, input rejection, and accounting invariants over 90 scenarios. CI is configured for Python 3.10, 3.12, and 3.14; its remote result is separate from the local test result.

Development used OpenAI Codex assistance. The repository contains runnable evidence and explicit modeling choices for independent review. MIT-licensed original code.
