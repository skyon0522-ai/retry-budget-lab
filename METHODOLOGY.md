# Model, accounting, and limits

## Event engine

`retry_budget_lab.py` contains the configuration, one event loop, percentile calculation, aggregation, and CLI. `tests/test_simulation.py` checks behavior without network access or real sleeping. Runtime code uses only the Python standard library.

The engine advances a floating-point clock to the next event in a heap. Events at the same timestamp execute in this order: deadline, completion, arrival. Insertion order breaks ties within one event type. Initial requests enter in request-ID order. Queued attempts start in FIFO order immediately after a completion frees a server. A deadline removes queued work logically; its stale queue entry is skipped when reached. Running work keeps its server even after the client expires.

An outage represents a dependency returning retryable failures while still consuming a fixed service duration. It is not a total suspension of the server's ability to process work. The outcome is selected at service start. For example, a 0.1-second attempt starting at 0.25 seconds fails when recovery occurs at 0.30 seconds, even though its completion is later. All logical requests arrive at zero and have the same deadline.

The backoff window doubles after each failure and saturates at the configured cap. The state update avoids constructing a huge exponential. Zero base or cap means immediate retry after the preceding service completion; positive service duration prevents an infinite zero-time loop. The attempt limit remains in force. Full jitter uses a run-local `random.Random(seed)` instance. It can consume attempt allowance earlier than capped backoff during an outage.

This is a continuous-time discrete-event model using binary floating-point seconds, without fixed simulation ticks or histogram bins. Near-boundary results follow the represented floating-point timestamps. Tests pin exact representable deadline ties; this is not a real-time scheduler.

## Metrics and conservation

| Metric | Definition |
|---|---|
| `successes`, `misses` | Terminal logical-request outcomes; sum to `clients`. |
| `deadline_misses` | No success strictly before the deadline, unless a different terminal reason occurred first. |
| `attempt_limit_misses` | Final allowed attempt failed before the deadline. |
| `retry_budget_misses` | A due retry could not be admitted because the shared retry cap was exhausted. |
| `attempts`, `retry_attempts` | Attempts admitted to service or queue; first attempts are included only in `attempts`. |
| `attempts_started`, `attempts_completed` | Attempts that occupied a server. All started work drains to completion. |
| `queued_attempts_abandoned` | Admitted attempts removed by deadline before service started. |
| `load_amplification` | Admitted attempts divided by original logical requests; includes queued attempts later abandoned. |
| `peak_queue` | Maximum waiting attempts, excluding in-service work. |
| `peak_backlog` | Maximum waiting plus in-service attempts, including running work whose caller has expired. |
| `peak_busy_servers` | Maximum concurrent in-service attempts; at most `servers`. |
| `service_work_seconds` | Started attempts times service duration, including failed and late work. |
| `service_work_after_deadline_seconds` | Sum of the portions of in-service attempts executed at times beyond the deadline. |
| `completions_at_or_after_deadline` | Running attempts whose caller had already expired when they completed; equality counts. |
| `last_completion_seconds` | Final actual completion, including late work; excludes no-op deadline events. |
| `last_request_terminal_seconds` | Time when the last request acquired a terminal outcome. |
| `success_latency_seconds` | Nearest-rank p50/p95/p99 of successful end-to-end latencies only. Null when there are no successes. |

The tests require these independent accounting relations:

```text
successes + misses = clients
misses = deadline_misses + attempt_limit_misses + retry_budget_misses
attempts = clients + retry_attempts
attempts = attempts_started + queued_attempts_abandoned
attempts_started = attempts_completed
attempts = sum(attempts_per_request)
retry_attempts <= retry_budget                  # when a budget is supplied
1 <= attempts_per_request <= max_attempts
```

The first attempt is always admitted because the deadline must be positive. Retry tokens are spent only on admitted arrivals, not on backoff plans that never reach their due time. Tokens are not refunded if queued attempts later expire.

Per-policy aggregates report mean/min/max for each run metric. Pooled latency combines all successful requests across the listed seeds; it is neither the mean of run percentiles nor an all-request latency measure. Seeds are distinct and use equal request counts. Ranges over five seeds are sensitivity observations, not confidence intervals. Capped backoff uses no random draws and therefore repeats exactly across seeds.

## Limitations and valid use

- One simultaneous burst, identical request sizes, constant server capacity, one deterministic outage, FIFO scheduling, and an unlimited waiting room. These assumptions can smooth retry timing or dominate the reported peak queue.
- No attempt timeout, overlapping retry, hedging, partial success, jittered service times, network delay, arrivals after time zero, circuit breaker, rate-limit response, adaptive throttling, or changing capacity.
- A shared budget is a fixed global counter for the run. Distributed budget coordination, fairness, replenishment, tenant quotas, and monetary/token budgets are not modeled.
- Deadlines stop future client work and cancel queued service, but never preempt a running attempt. A real dependency may have different cancellation behavior.
- The same seed identifies a reproducible run with this code and compatible Python runtime. Pin the version and environment for archival experiments. Small decimal differences are not performance differences.
- None of the checked-in scenarios were calibrated against a customer or provider. The results cannot establish a production SLO, optimum setting, provider capacity, financial saving, or workload-independent advantage for a policy.

Use the examples to examine tradeoffs and accounting, then validate the model against traces from the integration being designed. A useful next experiment changes one documented assumption while keeping a comparison baseline; adding a large policy framework would obscure that purpose.
