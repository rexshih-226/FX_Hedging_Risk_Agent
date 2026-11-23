"""Generate checked-in JSON Schema and demo assets; no external requests."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://risk-agent.local/schemas/"


def save(name, data):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def obj(properties, required=None):
    return {"type": "object", "properties": properties, "required": list(properties) if required is None else required, "additionalProperties": False}


def array(items, **extra):
    return {"type": "array", "items": items, **extra}


def enum(*items):
    return {"enum": list(items)}


def ref(name):
    return {"$ref": BASE + "common.json#/$defs/" + name}


def schema(name, body):
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": BASE + name + ".json", **body}


text = {"type": "string", "minLength": 1}
currency = {"type": "string", "pattern": "^[A-Z]{3}$"}
timestamp = {"type": "string", "format": "date-time", "pattern": "(Z|[+-][0-9]{2}:[0-9]{2})$"}
day = {"type": "string", "format": "date"}
positive = {"type": "number", "exclusiveMinimum": 0}
nonnegative = {"type": "number", "minimum": 0}
integer = {"type": "integer", "minimum": 1}
hash_value = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
trade = obj({"trade_id": text, "product": enum("deliverable_forward"), "currency": currency,
             "direction": enum("BUY_BASE", "SELL_BASE"), "notional": positive,
             "maturity_date": day, "forward_rate": positive, "fee_usd": nonnegative})
check = obj({"code": text, "status": enum("PASS", "REVISE", "NEEDS_DATA", "HUMAN_REVIEW"),
             "owner": enum("RISK", "STRATEGY", "ERP", "FX", "ERP_FX", "HUMAN"), "message": text,
             "actual": {"type": ["number", "null"]}, "limit": {"type": ["number", "null"]}})
external = obj({"area": text, "status": enum("NOT_IMPLEMENTED"), "source_ids": array(text, minItems=1)})
defs = {"trade": trade, "check": check, "external": external}
save("schemas/common.json", schema("common", {"$defs": defs}))

phase1 = obj({
    "schema_version": {"const": "1.0"}, "case_id": text, "mode": enum("DEMO", "LIVE"), "as_of": timestamp,
    "entity": obj({"entity_id": text, "name": text, "jurisdiction": text, "tax_residency": text,
                   "functional_currency": currency, "accounting_basis": enum("US_GAAP", "IFRS", "OTHER")}),
    "counterparty": obj({"counterparty_id": text, "name": text, "jurisdiction": text, "branch": text}),
    "exposure": obj({"exposure_id": text, "currency": currency, "exposure_amount": {"type": "number", "not": {"const": 0}},
                     "maturity_date": day, "purpose": enum("OPERATING_EXPENSE", "MONETARY_ASSET_LIABILITY")}),
    "existing_hedges": array(ref("trade")),
    "market": obj({"snapshot_id": text, "as_of": timestamp, "base_currency": currency, "quote_currency": currency, "spot": positive}),
})
save("schemas/phase1_input.json", schema("phase1_input", phase1))
constraints = obj({
    "exposure_id": text, "max_hedge_ratio": {"type": "number", "minimum": 0, "maximum": 1},
    "hedge_ratio_basis": {"const": "GROSS_NOTIONAL"}, "include_existing_hedges": {"const": True},
    "existing_notional": nonnegative, "max_new_notional": nonnegative, "notional_currency": currency,
    "allowed_products": {"const": ["deliverable_forward"]}, "required_direction": enum("BUY_BASE", "SELL_BASE"),
    "required_maturity_date": day, "max_stress_loss_usd": nonnegative,
    "spot_shocks": array({"type": "number", "exclusiveMinimum": -1}, minItems=2, uniqueItems=True), "market_snapshot_id": text,
})
phase1_out = obj({
    "schema_version": {"const": "1.0"}, "case_id": text, "status": enum("PREPARED", "NEEDS_DATA", "HUMAN_REVIEW"),
    "constraint_bundle_id": text, "context_hash": hash_value, "policy_version": text, "policy_hash": hash_value,
    "created_at": timestamp, "valid_until": timestamp, "approval_scope": {"const": "DEMO_POLICY_ONLY"},
    "execution_allowed": {"const": False}, "constraints": constraints, "checks": array(ref("check")),
    "external_reviews": array(ref("external"), minItems=5), "next_action": enum("SEND_TO_STRATEGY", "REFRESH_CONTEXT", "ESCALATE"),
})
save("schemas/phase1_output.json", schema("phase1_output", phase1_out))
proposal = obj({"proposal_id": text, "version": integer, "market_snapshot_id": text, "legs": array(ref("trade"))})
phase2 = obj({"schema_version": {"const": "1.0"}, "case_id": text, "constraint_bundle_id": text, "context_hash": hash_value, "proposal": proposal})
save("schemas/phase2_input.json", schema("phase2_input", phase2))
scenario = obj({"shock": {"type": "number"}, "spot": positive, "exposure_pnl_usd": {"type": "number"},
                "hedge_pnl_usd": {"type": "number"}, "fees_usd": nonnegative, "loss_usd": nonnegative})
phase2_out = obj({
    "schema_version": {"const": "1.0"}, "case_id": text, "proposal_id": text, "proposal_version": integer,
    "proposal_hash": hash_value, "constraint_bundle_id": text, "policy_version": text, "evaluated_at": timestamp,
    "decision": enum("APPROVE", "REVISE", "NEEDS_DATA", "HUMAN_REVIEW"), "review_attempt": integer,
    "approval_scope": {"const": "DEMO_POLICY_ONLY"}, "execution_allowed": {"const": False},
    "checks": array(ref("check")), "stress_scenarios": array(scenario), "external_reviews": array(ref("external"), minItems=5),
    "next_action": enum("DEMO_COMPLETE", "REOPTIMIZE", "REFRESH_CONTEXT", "ESCALATE"),
})
save("schemas/phase2_output.json", schema("phase2_output", phase2_out))
policy = obj({
    "version": text, "status": {"const": "APPROVED_DEMO"}, "source_id": {"const": "simulation_policy"},
    "description": text, "effective_from": day, "effective_to": day,
    "max_hedge_ratio": {"type": "number", "minimum": 0, "maximum": 1}, "max_stress_loss_usd": nonnegative,
    "spot_shocks": {"const": [-0.1, 0.1]}, "max_market_age_seconds": integer,
    "max_context_age_seconds": integer, "bundle_ttl_seconds": integer, "max_review_attempts": integer,
})
save("schemas/policy.json", schema("policy", policy))
save("examples/demo_policy.json", {
    "version": "DEMO-POLICY-2026-11-v1", "status": "APPROVED_DEMO", "source_id": "simulation_policy",
    "description": "作業模擬政策；不是 NVIDIA 真實政策、董事會決議或法定比例。",
    "effective_from": "2026-01-01", "effective_to": "2027-01-01",
    "max_hedge_ratio": 0.8, "max_stress_loss_usd": 80000,
    "spot_shocks": [-0.1, 0.1], "max_market_age_seconds": 900,
    "max_context_age_seconds": 3600, "bundle_ttl_seconds": 900, "max_review_attempts": 3,
})
save("examples/phase1_input.json", {
    "schema_version": "1.0", "case_id": "NVDA-DEMO-001", "mode": "DEMO", "as_of": "2026-11-23T02:00:00Z",
    "entity": {"entity_id": "NVDA-US-DEMO", "name": "NVIDIA-background simulated treasury",
               "jurisdiction": "US", "tax_residency": "US", "functional_currency": "USD", "accounting_basis": "US_GAAP"},
    "counterparty": {"counterparty_id": "BANK-DEMO", "name": "Simulated US bank", "jurisdiction": "US", "branch": "US-DEMO"},
    "exposure": {"exposure_id": "EXP-EUR-001", "currency": "EUR", "exposure_amount": -3000000,
                 "maturity_date": "2027-01-22", "purpose": "OPERATING_EXPENSE"},
    "existing_hedges": [{"trade_id": "OLD-001", "product": "deliverable_forward", "currency": "EUR",
                         "direction": "BUY_BASE", "notional": 900000, "maturity_date": "2027-01-22", "forward_rate": 1.1, "fee_usd": 0}],
    "market": {"snapshot_id": "SIM-EURUSD-001", "as_of": "2026-11-23T02:00:00Z", "base_currency": "EUR", "quote_currency": "USD", "spot": 1.1},
})
save("examples/phase2_input.json", {
    "schema_version": "1.0", "case_id": "NVDA-DEMO-001", "constraint_bundle_id": "REPLACED_BY_EXAMPLE_GENERATOR",
    "context_hash": "0" * 64,
    "proposal": {"proposal_id": "PROPOSAL-001", "version": 1, "market_snapshot_id": "SIM-EURUSD-001",
                 "legs": [{"trade_id": "NEW-001", "product": "deliverable_forward", "currency": "EUR", "direction": "BUY_BASE",
                           "notional": 1800000, "maturity_date": "2027-01-22", "forward_rate": 1.1, "fee_usd": 1000}]},
})
