import copy
import json
from pathlib import Path
import unittest

from performance_metrics import evaluate, summarize


class MetricsTest(unittest.TestCase):
    def setUp(self):
        self.goals = json.loads(Path(__file__).with_name("performance_goals.json").read_text(encoding="utf-8"))
        self.samples = [{"operation": operation, "ms": 10, "ok": True, "status": 200}
                        for operation in self.goals["latency_ms"] for _ in range(100)]
        self.summary = summarize(self.samples, elapsed=10)

    def test_valid_evidence_passes(self):
        self.assertTrue(evaluate(self.summary, self.goals, True)["passed"])

    def test_insufficient_samples_cannot_pass(self):
        summary = copy.deepcopy(self.summary)
        summary["operations"]["payment"]["samples"] = 99
        self.assertFalse(evaluate(summary, self.goals, True)["passed"])

    def test_slow_tail_is_not_hidden_by_fast_majority(self):
        for sample in self.samples[:2]:
            sample["ms"] = 5000
        summary = summarize(self.samples, 10)
        self.assertEqual(summary["operations"]["catalog"]["p95_ms"], 10)
        self.assertFalse(evaluate(summary, self.goals, True)["passed"])

    def test_polling_does_not_inflate_useful_throughput(self):
        with_polls = self.samples + [{"operation": "order_poll", "ms": 10, "ok": True, "status": 200}] * 10000
        summary = summarize(with_polls, 10)
        self.assertEqual(summary["useful_requests_per_second"], self.summary["useful_requests_per_second"])
        self.assertGreater(summary["requests_per_second"], self.summary["requests_per_second"])

    def test_errors_at_limit_fail(self):
        summary = copy.deepcopy(self.summary)
        summary["error_percent"] = 1
        self.assertFalse(evaluate(summary, self.goals, True)["passed"])

    def test_incorrect_business_results_fail_even_with_low_latency(self):
        self.assertFalse(evaluate(self.summary, self.goals, False)["passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
