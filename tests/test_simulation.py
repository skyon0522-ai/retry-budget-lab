import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from retry_budget_lab import Config, experiment, latency_summary, simulate


class SimulationTests(unittest.TestCase):
    def test_one_client_without_outage(self):
        run = simulate(Config(clients=1, servers=1, outage_seconds=0), "capped", 0)
        self.assertEqual(run.metrics["successes"], 1)
        self.assertEqual(run.metrics["attempts"], 1)
        self.assertEqual(run.success_latencies, [0.02])
        self.assertEqual(run.metrics["peak_queue"], 0)

    def test_exact_fifo_capacity(self):
        config = Config(
            clients=4, servers=2, service_seconds=1, outage_seconds=0, deadline_seconds=3
        )
        run = simulate(config, "capped", 0)
        self.assertEqual(run.success_latencies, [1, 1, 2, 2])
        self.assertEqual(run.metrics["peak_queue"], 2)
        self.assertEqual(run.metrics["peak_backlog"], 4)
        self.assertEqual(run.metrics["peak_busy_servers"], 2)

    def test_retry_recovers_after_outage(self):
        config = Config(
            clients=1, servers=1, service_seconds=0.1, outage_seconds=0.1, base_seconds=0.2
        )
        run = simulate(config, "capped", 0)
        self.assertEqual(run.metrics["attempts"], 2)
        self.assertEqual(run.metrics["successes"], 1)
        self.assertAlmostEqual(run.success_latencies[0], 0.4)

    def test_max_attempts_one_disables_retries(self):
        config = Config(clients=3, servers=3, outage_seconds=10, max_attempts=1)
        for policy in ("capped", "full-jitter"):
            run = simulate(config, policy, 2)
            self.assertEqual(run.metrics["attempts"], 3)
            self.assertEqual(run.metrics["retry_attempts"], 0)
            self.assertEqual(run.metrics["attempt_limit_misses"], 3)

    def test_shared_budget_is_exact_and_first_attempts_are_free(self):
        config = Config(
            clients=3, servers=3, outage_seconds=10, deadline_seconds=10, retry_budget=2
        )
        run = simulate(config, "full-jitter", 0)
        self.assertEqual(run.metrics["retry_attempts"], 2)
        self.assertEqual(run.metrics["attempts"], 5)
        self.assertEqual(run.metrics["retry_budget_misses"], 3)
        zero = simulate(replace(config, retry_budget=0), "capped", 0)
        self.assertEqual(zero.metrics["attempts"], 3)

    def test_deadline_wins_completion_tie(self):
        config = Config(
            clients=1, servers=1, service_seconds=1, outage_seconds=0, deadline_seconds=1
        )
        run = simulate(config, "capped", 0)
        self.assertEqual(run.metrics["successes"], 0)
        self.assertEqual(run.metrics["deadline_misses"], 1)
        self.assertEqual(run.metrics["completions_at_or_after_deadline"], 1)
        self.assertEqual(run.success_latencies, [])

    def test_expired_queue_does_not_start_and_running_work_drains(self):
        config = Config(
            clients=3, servers=1, service_seconds=1, outage_seconds=0, deadline_seconds=0.5
        )
        run = simulate(config, "capped", 0)
        self.assertEqual(run.metrics["deadline_misses"], 3)
        self.assertEqual(run.metrics["attempts_started"], 1)
        self.assertEqual(run.metrics["queued_attempts_abandoned"], 2)
        self.assertEqual(run.metrics["last_completion_seconds"], 1)
        self.assertEqual(run.metrics["service_work_after_deadline_seconds"], 0.5)

    def test_retry_at_deadline_is_not_admitted(self):
        config = Config(
            clients=1,
            service_seconds=0.25,
            outage_seconds=10,
            deadline_seconds=0.5,
            base_seconds=0.25,
        )
        run = simulate(config, "capped", 0)
        self.assertEqual(run.metrics["attempts"], 1)
        self.assertEqual(run.metrics["deadline_misses"], 1)

    def test_same_seed_is_identical(self):
        self.assertEqual(experiment(Config(), [2, 9]), experiment(Config(), [2, 9]))

    def test_report_keeps_original_seed_provenance(self):
        seeds = [0, 1]
        report = experiment(Config(clients=1, outage_seconds=0), seeds)
        seeds[0] = 999
        seeds.append(2)
        self.assertEqual(report["seeds"], [0, 1])
        for comparison in report["comparisons"].values():
            self.assertEqual([run["seed"] for run in comparison["runs"]], [0, 1])

    def test_finite_metrics_do_not_overflow_during_aggregation(self):
        config = Config(
            clients=1,
            servers=1,
            service_seconds=6e307,
            deadline_seconds=6e307,
            outage_seconds=0,
        )
        report = experiment(config, [0, 1, 2, 3, 4])
        for comparison in report["comparisons"].values():
            for key in ("service_work_seconds", "last_completion_seconds"):
                self.assertEqual(
                    comparison["aggregate"][key],
                    {"mean": 6e307, "min": 6e307, "max": 6e307},
                )

    def test_nonfinite_calculated_metrics_are_rejected_before_output(self):
        config = Config(
            clients=3,
            servers=3,
            service_seconds=6e307,
            deadline_seconds=6e307,
            outage_seconds=0,
        )
        with self.assertRaisesRegex(ValueError, "service_work_seconds.*finite float range"):
            experiment(config, [0])

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            output.write_text("preserve this\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "retry_budget_lab",
                    "--clients",
                    "3",
                    "--servers",
                    "3",
                    "--service-seconds",
                    "6e307",
                    "--deadline-seconds",
                    "6e307",
                    "--outage-seconds",
                    "0",
                    "--seeds",
                    "0",
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("finite float range", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "preserve this\n")

    def test_zero_backoff_has_same_semantics_under_both_policies(self):
        config = Config(clients=7, servers=2, base_seconds=0)
        self.assertEqual(simulate(config, "capped", 0), simulate(config, "full-jitter", 8))

    def test_capped_policy_has_no_seed_dependence(self):
        self.assertEqual(simulate(Config(), "capped", 0), simulate(Config(), "capped", 999))

    def test_capped_window_doubles_and_stays_at_cap(self):
        config = Config(
            clients=1,
            servers=1,
            service_seconds=1,
            outage_seconds=100,
            deadline_seconds=100,
            base_seconds=1,
            cap_seconds=2,
            max_attempts=5,
        )
        run = simulate(config, "capped", 0)
        # Five seconds of service plus waits of 1, 2, 2, and 2 seconds.
        self.assertEqual(run.metrics["last_request_terminal_seconds"], 12)
        self.assertEqual(run.metrics["attempts"], 5)

    def test_jitter_changes_timing_within_the_first_window(self):
        config = Config(clients=1, outage_seconds=0.02, base_seconds=0.2)
        first = simulate(config, "full-jitter", 0)
        second = simulate(config, "full-jitter", 1)
        self.assertNotEqual(first.success_latencies, second.success_latencies)
        for run in (first, second):
            self.assertEqual(run.metrics["attempts"], 2)
            self.assertGreaterEqual(run.success_latencies[0], 0.04)
            self.assertLess(run.success_latencies[0], 0.24)

    def test_conservation_and_bounds_across_scenarios(self):
        for policy in ("capped", "full-jitter"):
            for seed in range(5):
                for budget in (None, 0, 9):
                    for deadline in (0.01, 0.1, 1.0):
                        with self.subTest(
                            policy=policy, seed=seed, budget=budget, deadline=deadline
                        ):
                            config = Config(
                                clients=17,
                                servers=3,
                                retry_budget=budget,
                                deadline_seconds=deadline,
                            )
                            run = simulate(config, policy, seed)
                            m = run.metrics
                            self.assertEqual(m["successes"] + m["misses"], config.clients)
                            self.assertEqual(
                                m["misses"],
                                m["deadline_misses"]
                                + m["attempt_limit_misses"]
                                + m["retry_budget_misses"],
                            )
                            self.assertEqual(m["attempts"], sum(run.attempts_per_request))
                            self.assertEqual(m["attempts"], config.clients + m["retry_attempts"])
                            self.assertEqual(
                                m["attempts"],
                                m["attempts_started"] + m["queued_attempts_abandoned"],
                            )
                            self.assertEqual(m["attempts_started"], m["attempts_completed"])
                            self.assertLessEqual(m["peak_busy_servers"], config.servers)
                            self.assertLessEqual(m["peak_backlog"], config.clients)
                            self.assertTrue(
                                all(1 <= n <= config.max_attempts for n in run.attempts_per_request)
                            )
                            self.assertTrue(all(t < deadline for t in run.success_latencies))
                            if budget is not None:
                                self.assertLessEqual(m["retry_attempts"], budget)

    def test_missing_successes_are_null(self):
        self.assertEqual(latency_summary([]), {"p50": None, "p95": None, "p99": None})
        self.assertEqual(latency_summary([4, 1, 3, 2]), {"p50": 2, "p95": 4, "p99": 4})

    def test_validation(self):
        for kwargs in (
            {"clients": 0},
            {"servers": -1},
            {"max_attempts": True},
            {"retry_budget": -1},
            {"service_seconds": 0},
            {"deadline_seconds": 0},
            {"outage_seconds": float("nan")},
            {"base_seconds": -1},
            {"cap_seconds": float("inf")},
            {"service_seconds": 1e308, "deadline_seconds": 1e308},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Config(**kwargs)
        for seeds in ([], [1, 1], [True]):
            with self.assertRaises(ValueError):
                experiment(Config(), seeds)
        with self.assertRaises(ValueError):
            simulate(Config(), "unknown", 1)

    def test_cli_json_and_invalid_argument(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "retry_budget_lab",
                "--clients",
                "1",
                "--outage-seconds",
                "0",
                "--seeds",
                "7",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(result.stdout)["seeds"], [7])
        invalid = subprocess.run(
            [sys.executable, "-m", "retry_budget_lab", "--clients", "0"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("positive integer", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
