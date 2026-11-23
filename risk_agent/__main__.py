import argparse
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from uuid import uuid4

from .agent import RiskAgent
from .contracts import ROOT, parse_time, read_json, write_json
from .ingestion import fetch_source
from .storage import Store


def demo():
    directory = ROOT / "artifacts" / "demo"
    directory.mkdir(parents=True, exist_ok=True)
    store = Store(directory / "risk.sqlite")
    request = read_json(ROOT / "examples" / "phase1_input.json")
    request["case_id"] += "-" + uuid4().hex[:8]
    clock = parse_time(request["as_of"]) + timedelta(seconds=60)
    agent = RiskAgent(store, read_json(ROOT / "examples" / "demo_policy.json"), clock=lambda: clock)
    bundle = agent.prepare(request)
    review = read_json(ROOT / "examples" / "phase2_input.json")
    review.update(case_id=request["case_id"], constraint_bundle_id=bundle["constraint_bundle_id"], context_hash=bundle["context_hash"])
    for name, value in [("phase1_input", request), ("phase1_output", bundle), ("phase2_input", review)]:
        write_json(directory / f"{name}.json", value)
    rejected = agent.review(review)
    write_json(directory / "phase2_revise.json", rejected)
    corrected = deepcopy(review)
    corrected["proposal"]["version"] = 2
    corrected["proposal"]["legs"][0]["notional"] = 1500000
    approved = agent.review(corrected)
    write_json(directory / "phase2_corrected_input.json", corrected)
    write_json(directory / "phase2_output.json", approved)
    store.close()
    return {"output_directory": str(directory), "prepare": bundle["status"], "first_review": rejected["decision"], "second_review": approved["decision"], "execution_allowed": approved["execution_allowed"], "clock": "Frozen demo clock; not a live quote"}


def main():
    parser = argparse.ArgumentParser(description="NVIDIA-background risk scaffold; demo approvals only")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo")
    for command in ("prepare", "review"):
        sub = commands.add_parser(command)
        sub.add_argument("--input", required=True)
        sub.add_argument("--db", default="artifacts/risk.sqlite")
        sub.add_argument("--policy", default=str(ROOT / "examples" / "demo_policy.json"))
        sub.add_argument("--at", help="Optional frozen evaluation clock for DEMO requests only")
    fetch = commands.add_parser("fetch")
    fetch.add_argument("source_id")
    fetch.add_argument("--user-agent", required=True)
    fetch.add_argument("--db", default="artifacts/risk.sqlite")
    fetch.add_argument("--output", default="artifacts/sources")
    args = parser.parse_args()
    if args.command == "demo":
        result = demo()
    else:
        store = Store(args.db)
        try:
            if args.command == "fetch":
                result = fetch_source(args.source_id, args.user_agent, args.output, store)
            else:
                request = read_json(args.input)
                if args.at:
                    context = request if args.command == "prepare" else (store.case(request["case_id"]) or [None, {}])[1]
                    if context.get("mode") != "DEMO":
                        raise ValueError("--at 僅供 DEMO 使用")
                agent = RiskAgent(store, read_json(args.policy), clock=(lambda: parse_time(args.at)) if args.at else None)
                result = getattr(agent, args.command)(request)
        finally:
            store.close()
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
