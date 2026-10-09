"""A finite-capacity retry experiment. It never sends requests or sleeps."""

from __future__ import annotations

import argparse
import heapq
import json
import math
import random
import statistics
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

POLICIES = ("capped", "full-jitter")


@dataclass(frozen=True)
class Config:
    clients: int = 200
    servers: int = 10
    service_seconds: float = 0.02
    outage_seconds: float = 0.3
    deadline_seconds: float = 1.0
    max_attempts: int = 5
    base_seconds: float = 0.05
    cap_seconds: float = 0.5
    retry_budget: int | None = None

    def __post_init__(self) -> None:
        for name in ("clients", "servers", "max_attempts"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.retry_budget is not None and (
            type(self.retry_budget) is not int or self.retry_budget < 0
        ):
            raise ValueError("retry_budget must be a nonnegative integer or None")
        for name in (
            "service_seconds",
            "outage_seconds",
            "deadline_seconds",
            "base_seconds",
            "cap_seconds",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.service_seconds == 0 or self.deadline_seconds == 0:
            raise ValueError("service_seconds and deadline_seconds must be positive")
        if not math.isfinite(self.service_seconds + self.deadline_seconds):
            raise ValueError("service_seconds plus deadline_seconds must be finite")


@dataclass
class _Request:
    window: float
    attempts: int = 0
    location: str = "waiting"
    outcome: str | None = None


@dataclass
class Run:
    metrics: dict[str, int | float]
    success_latencies: list[float]
    attempts_per_request: list[int]


def latency_summary(values: list[float]) -> dict[str, float | None]:
    """Nearest-rank percentiles; missing successes produce null, never zero."""
    ordered = sorted(values)
    return {
        name: ordered[math.ceil(q * len(ordered)) - 1] if ordered else None
        for name, q in (("p50", 0.5), ("p95", 0.95), ("p99", 0.99))
    }


def simulate(config: Config, policy: str, seed: int) -> Run:
    """Run a simultaneous arrival burst through a FIFO, finite-server queue.

    An attempt started during the outage fails after consuming service time.
    Every request has one end-to-end deadline and at most one in-flight attempt.
    Deadline events win ties with completions. In-service work is not cancelled.
    """
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}")
    rng = random.Random(seed)
    requests = [
        _Request(min(config.base_seconds, config.cap_seconds)) for _ in range(config.clients)
    ]
    # (time, priority, insertion order, request ID, failed-at-start)
    events: list[tuple[float, int, int, int, bool]] = []
    queue: deque[int] = deque()
    serial = 0
    busy = queued = accepted = retries = started = completed = 0
    abandoned = late = peak_queue = peak_backlog = peak_busy = 0
    last_completion = last_terminal = work_after_deadline = 0.0
    latencies: list[float] = []

    def schedule(when: float, priority: int, rid: int, failed: bool = False) -> None:
        nonlocal serial
        heapq.heappush(events, (when, priority, serial, rid, failed))
        serial += 1

    def finish(rid: int, outcome: str, now: float) -> None:
        nonlocal last_terminal
        requests[rid].outcome = outcome
        last_terminal = max(last_terminal, now)

    def start(rid: int, now: float) -> None:
        nonlocal busy, started, peak_busy
        requests[rid].location = "running"
        busy += 1
        started += 1
        peak_busy = max(peak_busy, busy)
        schedule(now + config.service_seconds, 1, rid, now < config.outage_seconds)

    for rid in range(config.clients):
        schedule(config.deadline_seconds, 0, rid)
        schedule(0.0, 2, rid)

    while events:
        now, kind, _, rid, failed = heapq.heappop(events)
        request = requests[rid]
        if kind == 0:  # Deadline: remove queued work, but let running work drain.
            if request.outcome is None:
                if request.location == "queued":
                    queued -= 1
                    abandoned += 1
                finish(rid, "deadline", now)
        elif kind == 1:  # Completion: the occupied server becomes available.
            busy -= 1
            completed += 1
            last_completion = now
            work_after_deadline += max(0.0, now - config.deadline_seconds)
            if request.outcome is not None:
                late += 1
            elif not failed:
                latencies.append(now)
                finish(rid, "success", now)
            elif request.attempts == config.max_attempts:
                finish(rid, "attempt_limit", now)
            else:
                request.location = "waiting"
                delay = request.window
                if policy == "full-jitter":
                    delay *= rng.random()
                request.window = min(config.cap_seconds, request.window * 2)
                # The existing deadline event will close requests that cannot retry.
                if now + delay < config.deadline_seconds:
                    schedule(now + delay, 2, rid)
            while queue and busy < config.servers:
                next_rid = queue.popleft()
                if requests[next_rid].outcome is None:
                    queued -= 1
                    start(next_rid, now)
        else:  # Arrival: first attempts are free; retries share a run-wide cap.
            if request.outcome is not None:
                continue
            if request.attempts:
                if config.retry_budget is not None and retries >= config.retry_budget:
                    finish(rid, "retry_budget", now)
                    continue
                retries += 1
            request.attempts += 1
            accepted += 1
            if busy < config.servers:
                start(rid, now)
            else:
                request.location = "queued"
                queue.append(rid)
                queued += 1
            peak_queue = max(peak_queue, queued)
            peak_backlog = max(peak_backlog, queued + busy)

    counts = {
        outcome: sum(r.outcome == outcome for r in requests)
        for outcome in ("success", "deadline", "attempt_limit", "retry_budget")
    }
    metrics = {
        "successes": counts["success"],
        "misses": config.clients - counts["success"],
        "deadline_misses": counts["deadline"],
        "attempt_limit_misses": counts["attempt_limit"],
        "retry_budget_misses": counts["retry_budget"],
        "attempts": accepted,
        "retry_attempts": retries,
        "attempts_started": started,
        "attempts_completed": completed,
        "queued_attempts_abandoned": abandoned,
        "completions_at_or_after_deadline": late,
        "load_amplification": accepted / config.clients,
        "peak_queue": peak_queue,
        "peak_backlog": peak_backlog,
        "peak_busy_servers": peak_busy,
        "service_work_seconds": started * config.service_seconds,
        "service_work_after_deadline_seconds": work_after_deadline,
        "last_completion_seconds": last_completion,
        "last_request_terminal_seconds": last_terminal,
    }
    return Run(metrics, latencies, [r.attempts for r in requests])


def _mean(values: list[int | float]) -> float:
    try:
        return statistics.fmean(values)
    except OverflowError:
        return float(statistics.mean(values))


def experiment(config: Config, seeds: list[int]) -> dict:
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be a nonempty list of distinct integers")
    if any(type(seed) is not int for seed in seeds):
        raise ValueError("seeds must be integers")
    seeds = list(seeds)
    comparisons = {}
    for policy in POLICIES:
        runs = [simulate(config, policy, seed) for seed in seeds]
        summaries = {
            key: {"mean": _mean(values), "min": min(values), "max": max(values)}
            for key in runs[0].metrics
            for values in [[run.metrics[key] for run in runs]]
        }
        pooled = [latency for run in runs for latency in run.success_latencies]
        comparisons[policy] = {
            "runs": [
                {
                    "seed": seed,
                    **run.metrics,
                    "success_latency_seconds": latency_summary(run.success_latencies),
                }
                for seed, run in zip(seeds, runs, strict=True)
            ],
            "aggregate": summaries,
            "pooled_success_count": len(pooled),
            "pooled_success_latency_seconds": latency_summary(pooled),
        }
    return {
        "schema_version": 1,
        "config": asdict(config),
        "seeds": seeds,
        "comparisons": comparisons,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("clients", "servers", "max_attempts"):
        parser.add_argument(
            "--" + name.replace("_", "-"), type=int, default=getattr(Config(), name)
        )
    for name in (
        "service_seconds",
        "outage_seconds",
        "deadline_seconds",
        "base_seconds",
        "cap_seconds",
    ):
        parser.add_argument(
            "--" + name.replace("_", "-"), type=float, default=getattr(Config(), name)
        )
    parser.add_argument(
        "--retry-budget",
        type=int,
        default=None,
        help="total retry attempts admitted across the whole run",
    )
    parser.add_argument("--seeds", default="0,1,2,3,4")
    parser.add_argument("--output", type=Path, help="write JSON here instead of stdout")
    args = vars(parser.parse_args())
    output = args.pop("output")
    raw_seeds = args.pop("seeds")
    try:
        seeds = [int(value) for value in raw_seeds.split(",")]
        result = experiment(Config(**args), seeds)
    except ValueError as error:
        parser.error(str(error))
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output:
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
