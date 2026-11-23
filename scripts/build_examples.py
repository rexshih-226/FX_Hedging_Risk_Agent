"""Rebuild the four handoff examples with matching hashes and a frozen demo clock."""
from copy import deepcopy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from risk_agent.agent import RiskAgent
from risk_agent.contracts import ROOT, parse_time, read_json, write_json
from risk_agent.storage import Store

store = Store(":memory:")
context = read_json(ROOT / "examples" / "phase1_input.json")
agent = RiskAgent(store, read_json(ROOT / "examples" / "demo_policy.json"), clock=lambda: parse_time("2026-11-23T02:01:00Z"))
bundle = agent.prepare(context)
request = read_json(ROOT / "examples" / "phase2_input.json")
request.update(case_id=context["case_id"], constraint_bundle_id=bundle["constraint_bundle_id"], context_hash=bundle["context_hash"])
request["proposal"]["version"] = 1
request["proposal"]["legs"][0]["notional"] = 1800000
rejected = agent.review(request)
corrected = deepcopy(request)
corrected["proposal"]["version"] = 2
corrected["proposal"]["legs"][0]["notional"] = 1500000
approved = agent.review(corrected)
for name, value in [("phase1_output", bundle), ("phase2_input", request), ("phase2_revise", rejected), ("phase2_corrected_input", corrected), ("phase2_output", approved)]:
    write_json(ROOT / "examples" / f"{name}.json", value)
store.close()
