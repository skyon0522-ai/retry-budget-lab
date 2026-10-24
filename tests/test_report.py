import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retry_budget_lab import Config, experiment, main
from retry_budget_report import render_html


class ReportTests(unittest.TestCase):
    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(sys, "argv", ["retry-budget-lab", *arguments]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            try:
                main()
            except SystemExit as error:
                return error.code, stdout.getvalue(), stderr.getvalue()
        return 0, stdout.getvalue(), stderr.getvalue()

    def test_custom_cli_report_uses_same_experiment_and_actual_settings(self):
        config = Config(clients=3, servers=1, outage_seconds=0, retry_budget=0)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "custom"
            code, stdout, stderr = self.invoke(
                [
                    "--clients",
                    "3",
                    "--servers",
                    "1",
                    "--outage-seconds",
                    "0",
                    "--retry-budget",
                    "0",
                    "--seeds",
                    "7,11",
                    "--report-dir",
                    str(target),
                ]
            )
            self.assertEqual((code, stderr), (0, ""))
            self.assertIn(str(target / "report.html"), stdout)
            report = json.loads((target / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report, experiment(config, [7, 11]))
            html = " ".join((target / "report.html").read_text(encoding="utf-8").split())
            self.assertIn("Simulated requests: 3", html)
            self.assertIn("Server count: 1; service time: 0.02", html)
            self.assertIn("<code>7, 11</code>", html)
            self.assertIn("Shared retry admission cap</th><td>0</td>", html)
            self.assertNotIn("Forty", html)
            self.assertEqual(html.count("<td>7</td>"), 2)
            self.assertEqual(html.count("<td>11</td>"), 2)

    def test_zero_successes_show_absent_percentile_and_keep_report_unchanged(self):
        report = experiment(Config(clients=2, max_attempts=1, outage_seconds=10), [3])
        before = copy.deepcopy(report)
        html = render_html(report)
        self.assertEqual(html.count("No successes</td>"), 4)
        self.assertNotIn("0.000 s", html)
        self.assertEqual(report, before)

    def test_existing_paths_are_rejected_before_experiment_without_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "existing"
            directory.mkdir()
            sentinel = directory / "report.json"
            sentinel.write_bytes(b"previous experiment\n")
            file = Path(temporary) / "existing-file"
            file.write_bytes(b"leave intact")
            paths = [directory, file]
            if os.name == "posix":
                dangling = Path(temporary) / "dangling"
                dangling.symlink_to("does-not-exist")
                paths.append(dangling)
            for target in paths:
                with self.subTest(target=target.name), patch("retry_budget_lab.experiment") as run:
                    code, _, stderr = self.invoke(["--report-dir", str(target)])
                    self.assertEqual(code, 2)
                    self.assertIn("existing paths are not replaced", stderr)
                    run.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b"previous experiment\n")
            self.assertEqual(file.read_bytes(), b"leave intact")

    def test_output_modes_are_exclusive_and_invalid_input_creates_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "not-created"
            for arguments in (
                ["--report-dir", str(target), "--output", str(target / "old.json")],
                ["--report-dir", str(target), "--clients", "0"],
            ):
                with self.subTest(arguments=arguments):
                    self.assertEqual(self.invoke(arguments)[0], 2)
                    self.assertFalse(target.exists())

    def test_html_write_error_is_clear_and_does_not_hide_partial_json(self):
        original = Path.write_text

        def fail_html(path, *args, **kwargs):
            if path.name == "report.html":
                raise OSError("test storage failure")
            return original(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "partial"
            with patch("retry_budget_report.Path.write_text", autospec=True, side_effect=fail_html):
                code, _, stderr = self.invoke(
                    ["--clients", "1", "--seeds", "0", "--report-dir", str(target)]
                )
            self.assertEqual(code, 2)
            self.assertIn("test storage failure", stderr)
            self.assertIn("partial new report directory may remain", stderr)
            self.assertNotIn("Traceback", stderr)
            self.assertEqual(json.loads((target / "report.json").read_text())["seeds"], [0])
            self.assertFalse((target / "report.html").exists())

    def test_json_output_io_errors_are_clear_and_preserve_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "existing"
            directory.mkdir()
            sentinel = directory / "previous.json"
            sentinel.write_bytes(b"previous experiment\n")
            for target in (root / "missing" / "run.json", directory):
                with self.subTest(target=target):
                    code, stdout, stderr = self.invoke(
                        ["--clients", "1", "--seeds", "0", "--output", str(target)]
                    )
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("Cannot save JSON", stderr)
                    self.assertIn(repr(str(target)), stderr)
                    self.assertNotIn("Traceback", stderr)
            self.assertFalse((root / "missing").exists())
            self.assertEqual(list(directory.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_bytes(), b"previous experiment\n")

    def test_renderer_escapes_displayed_text(self):
        report = experiment(Config(clients=1, outage_seconds=0), [0])
        report["seeds"] = ["<script>alert(1)</script>"]
        html = render_html(report)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>", html)


if __name__ == "__main__":
    unittest.main()
