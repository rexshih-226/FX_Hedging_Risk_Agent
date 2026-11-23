from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from risk_agent.agent import RiskAgent
from risk_agent.contracts import ROOT, parse_time, read_json, validate
from risk_agent.storage import Store


class RiskAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "test.sqlite")
        self.context = read_json(ROOT / "examples" / "phase1_input.json")
        self.policy = read_json(ROOT / "examples" / "demo_policy.json")
        self.clock = parse_time(self.context["as_of"]) + timedelta(seconds=60)
        self.agent = RiskAgent(self.store, self.policy, clock=lambda: self.clock)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def proposal(self, notional=1500000, version=1):
        bundle = self.agent.prepare(self.context)
        request = read_json(ROOT / "examples" / "phase2_input.json")
        request.update(case_id=self.context["case_id"], constraint_bundle_id=bundle["constraint_bundle_id"], context_hash=bundle["context_hash"])
        request["proposal"]["version"] = version
        request["proposal"]["legs"][0]["notional"] = notional
        return request

    def test_prepare_subtracts_existing_hedges(self):
        result = self.agent.prepare(self.context)
        self.assertEqual(result["status"], "PREPARED")
        self.assertEqual(result["constraints"]["max_new_notional"], 1500000)

    def test_exact_ratio_and_cashflow_stress(self):
        result = self.agent.review(self.proposal())
        self.assertEqual(result["decision"], "APPROVE")
        self.assertFalse(result["execution_allowed"])
        adverse = next(x for x in result["stress_scenarios"] if x["shock"] == 0.1)
        self.assertAlmostEqual(adverse["loss_usd"], 67000)
        self.assertEqual(adverse["exposure_pnl_usd"], -330000)
        self.assertEqual(adverse["hedge_pnl_usd"], 264000)
        self.assertTrue(all(x["status"] == "NOT_IMPLEMENTED" for x in result["external_reviews"]))

    def test_receivable_sell_direction(self):
        self.context["exposure"]["exposure_amount"] = 3000000
        self.context["existing_hedges"][0]["direction"] = "SELL_BASE"
        request = self.proposal()
        request["proposal"]["legs"][0]["direction"] = "SELL_BASE"
        result = self.agent.review(request)
        self.assertEqual(result["decision"], "APPROVE")
        self.assertAlmostEqual(max(x["loss_usd"] for x in result["stress_scenarios"]), 67000)

    def test_overhedge_rejected(self):
        result = self.agent.review(self.proposal(1800000))
        self.assertEqual(result["decision"], "REVISE")
        self.assertIn("MAX_HEDGE_RATIO", [x["code"] for x in result["checks"] if x["status"] == "REVISE"])

    def test_no_hedge_is_not_free_pass(self):
        request = self.proposal()
        request["proposal"]["legs"] = []
        result = self.agent.review(request)
        self.assertEqual(result["decision"], "REVISE")
        self.assertIn("STRESS_LOSS", [x["code"] for x in result["checks"] if x["status"] == "REVISE"])

    def test_forward_rate_cost_included(self):
        request = self.proposal()
        request["proposal"]["legs"][0]["forward_rate"] = 1.2
        result = self.agent.review(request)
        self.assertEqual(result["decision"], "REVISE")
        self.assertAlmostEqual(max(x["loss_usd"] for x in result["stress_scenarios"]), 217000)

    def test_wrong_direction_skips_stress(self):
        request = self.proposal()
        request["proposal"]["legs"][0]["direction"] = "SELL_BASE"
        result = self.agent.review(request)
        self.assertEqual(result["decision"], "REVISE")
        self.assertEqual(result["stress_scenarios"], [])

    def test_wrong_maturity_rejected(self):
        request = self.proposal()
        request["proposal"]["legs"][0]["maturity_date"] = "2027-01-23"
        self.assertEqual(self.agent.review(request)["decision"], "REVISE")

    def test_duplicate_trade_rejected(self):
        request = self.proposal()
        request["proposal"]["legs"][0]["trade_id"] = "OLD-001"
        self.assertEqual(self.agent.review(request)["decision"], "REVISE")

    def test_old_quote_blocks_prepare(self):
        self.context["market"]["as_of"] = "2026-11-23T01:00:00Z"
        self.assertEqual(self.agent.prepare(self.context)["status"], "NEEDS_DATA")

    def test_future_quote_blocks_prepare(self):
        self.context["market"]["as_of"] = "2026-11-23T03:00:00Z"
        self.assertEqual(self.agent.prepare(self.context)["status"], "NEEDS_DATA")

    def test_expired_bundle_blocks_review(self):
        request = self.proposal()
        self.clock += timedelta(minutes=20)
        self.assertEqual(self.agent.review(request)["decision"], "NEEDS_DATA")

    def test_cross_border_routes_human(self):
        self.context["counterparty"]["jurisdiction"] = "DE"
        self.assertEqual(self.agent.prepare(self.context)["status"], "HUMAN_REVIEW")

    def test_live_mode_never_approved(self):
        self.context["mode"] = "LIVE"
        self.assertEqual(self.agent.review(self.proposal())["decision"], "HUMAN_REVIEW")

    def test_bundle_mismatch(self):
        request = self.proposal()
        request["context_hash"] = "0" * 64
        self.assertEqual(self.agent.review(request)["decision"], "NEEDS_DATA")

    def test_market_mismatch(self):
        request = self.proposal()
        request["proposal"]["market_snapshot_id"] = "different"
        self.assertEqual(self.agent.review(request)["decision"], "NEEDS_DATA")

    def test_retry_limit(self):
        self.assertEqual(self.agent.review(self.proposal(1800000, 1))["decision"], "REVISE")
        self.assertEqual(self.agent.review(self.proposal(1800000, 2))["decision"], "REVISE")
        self.assertEqual(self.agent.review(self.proposal(1800000, 3))["decision"], "HUMAN_REVIEW")

    def test_idempotency_and_version_protection(self):
        request = self.proposal(1800000)
        first = self.agent.review(request)
        self.assertEqual(self.agent.review(deepcopy(request)), first)
        self.assertEqual(len(self.store.reviews(self.context["case_id"])), 1)
        request["proposal"]["legs"][0]["notional"] = 1500000
        with self.assertRaises(ValueError):
            self.agent.review(request)

    def test_case_cannot_be_overwritten(self):
        self.agent.prepare(self.context)
        self.context["exposure"]["exposure_amount"] = -4000000
        with self.assertRaises(ValueError):
            self.agent.prepare(self.context)

    def test_changed_policy_requires_new_case(self):
        request = self.proposal()
        changed = deepcopy(self.policy)
        changed.update(version="DEMO-v2", max_hedge_ratio=0.7)
        agent = RiskAgent(self.store, changed, clock=lambda: self.clock)
        self.assertEqual(agent.review(request)["decision"], "HUMAN_REVIEW")

    def test_policy_same_version_immutable(self):
        changed = deepcopy(self.policy)
        changed["max_hedge_ratio"] = 0.7
        with self.assertRaises(ValueError):
            RiskAgent(self.store, changed)

    def test_schema_rejects_zero_exposure(self):
        self.context["exposure"]["exposure_amount"] = 0
        with self.assertRaises(ValueError):
            self.agent.prepare(self.context)

    def test_schema_rejects_naive_time(self):
        self.context["as_of"] = "2026-11-23T02:00:00"
        with self.assertRaises(ValueError):
            self.agent.prepare(self.context)

    def test_option_cannot_use_forward_pricer(self):
        request = self.proposal()
        request["proposal"]["legs"][0]["product"] = "option"
        with self.assertRaises(ValueError):
            self.agent.review(request)

    def test_unknown_case_rejected(self):
        request = self.proposal()
        request["case_id"] = "unknown"
        with self.assertRaises(ValueError):
            self.agent.review(request)

    def test_schemas_and_examples(self):
        from jsonschema import Draft202012Validator
        for path in (ROOT / "schemas").glob("*.json"):
            Draft202012Validator.check_schema(read_json(path))
        for name in ("phase1_input", "phase1_output", "phase2_input", "phase2_output"):
            validate(name, read_json(ROOT / "examples" / f"{name}.json"))


if __name__ == "__main__":
    unittest.main()
