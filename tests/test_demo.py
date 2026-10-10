import json
import tempfile
import unittest
from pathlib import Path

from demo import build_report, render_html, write_demo

ROOT = Path(__file__).resolve().parents[1]


class DemoTests(unittest.TestCase):
    def test_fixed_comparison_uses_existing_simulator_and_checked_output(self):
        report = build_report()
        existing = json.loads((ROOT / "examples/short-deadline.json").read_text(encoding="utf-8"))
        self.assertEqual(report, existing)
        self.assertEqual(report["config"]["clients"], 40)
        capped = report["comparisons"]["capped"]["aggregate"]
        jitter = report["comparisons"]["full-jitter"]["aggregate"]
        self.assertEqual(capped["successes"]["mean"], 40)
        self.assertEqual(jitter["successes"]["mean"], 32)
        self.assertGreater(jitter["attempts"]["mean"], capped["attempts"]["mean"])

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report"
            write_demo(output, report)
            self.assertEqual(
                json.loads((output / "report.json").read_text(encoding="utf-8")), report
            )
            self.assertEqual(
                (output / "report.html").read_text(encoding="utf-8"), render_html(report)
            )
            committed = ROOT / "examples/reports"
            self.assertEqual(
                (committed / "report.json").read_bytes(), (output / "report.json").read_bytes()
            )
            self.assertEqual(
                (committed / "report.html").read_bytes(), (output / "report.html").read_bytes()
            )
            before = (output / "report.json").read_bytes()
            with self.assertRaises(FileExistsError):
                write_demo(output, report)
            self.assertEqual((output / "report.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
