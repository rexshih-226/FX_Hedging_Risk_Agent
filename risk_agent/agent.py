"""Two-stage controller; LLM planning can later use the same bounded tools.

Mandatory checks cannot be skipped by a planner. APPROVE here is demo-only.
"""
from datetime import datetime, timedelta, timezone

from .checks import check_context, check_proposal, finding, number, stress_test
from .contracts import digest, parse_time, validate


class RiskAgent:
    def __init__(self, store, policy, clock=None):
        validate("policy", policy)
        self.store = store
        self.policy = policy
        self.store.save_policy(digest(policy), policy)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def now(self):
        return self.clock().isoformat().replace("+00:00", "Z")

    def prepare(self, request):
        validate("phase1_input", request)
        request_hash = digest({"input": request, "policy": self.policy})
        saved = self.store.case(request["case_id"])
        if saved:
            if saved[0] != request_hash:
                raise ValueError("case_id 已綁定其他資料／政策；請以新 case_id 重新準備")
            return saved[2]
        now = self.now()
        checks = check_context(request, self.policy, now)
        existing = sum((number(x["notional"]) for x in request["existing_hedges"]), number(0))
        cap = abs(number(request["exposure"]["exposure_amount"])) * number(self.policy["max_hedge_ratio"])
        if existing > cap:
            checks.append(finding("EXISTING_OVER_LIMIT", "HUMAN_REVIEW", "HUMAN", "既有部位已超過上限，新增避險無法修正"))
        status = "HUMAN_REVIEW" if any(c["status"] == "HUMAN_REVIEW" for c in checks) else "NEEDS_DATA" if checks else "PREPARED"
        expiry = min(
            parse_time(now) + timedelta(seconds=self.policy["bundle_ttl_seconds"]),
            parse_time(request["market"]["as_of"]) + timedelta(seconds=self.policy["max_market_age_seconds"]),
            parse_time(request["as_of"]) + timedelta(seconds=self.policy["max_context_age_seconds"]),
            parse_time(self.policy["effective_to"] + "T00:00:00Z"),
        )
        response = {
            "schema_version": "1.0", "case_id": request["case_id"], "status": status,
            "constraint_bundle_id": "bundle-" + request_hash, "context_hash": digest(request),
            "policy_version": self.policy["version"], "policy_hash": digest(self.policy),
            "created_at": now, "valid_until": expiry.isoformat().replace("+00:00", "Z"),
            "approval_scope": "DEMO_POLICY_ONLY", "execution_allowed": False,
            "constraints": {
                "exposure_id": request["exposure"]["exposure_id"],
                "max_hedge_ratio": self.policy["max_hedge_ratio"], "hedge_ratio_basis": "GROSS_NOTIONAL",
                "include_existing_hedges": True, "existing_notional": float(existing),
                "max_new_notional": float(max(cap - existing, number(0))),
                "notional_currency": request["exposure"]["currency"], "allowed_products": ["deliverable_forward"],
                "required_direction": "BUY_BASE" if request["exposure"]["exposure_amount"] < 0 else "SELL_BASE",
                "required_maturity_date": request["exposure"]["maturity_date"],
                "max_stress_loss_usd": self.policy["max_stress_loss_usd"],
                "spot_shocks": self.policy["spot_shocks"], "market_snapshot_id": request["market"]["snapshot_id"],
            },
            "checks": checks, "external_reviews": self.external_reviews(),
            "next_action": "SEND_TO_STRATEGY" if status == "PREPARED" else "REFRESH_CONTEXT" if status == "NEEDS_DATA" else "ESCALATE",
        }
        validate("phase1_output", response)
        self.store.save_case(request_hash, request, response)
        return response

    @staticmethod
    def external_reviews():
        return [{"area": area, "status": "NOT_IMPLEMENTED", "source_ids": ids} for area, ids in [
            ("US_DERIVATIVES", ["cftc", "ecfr"]),
            ("SANCTIONS", ["ofac"]), ("US_TAX", ["tax_cfr", "irs"]),
            ("US_GAAP", ["fasb"]), ("CROSS_BORDER", ["esma_emir"]),
        ]]

    def review(self, request):
        validate("phase2_input", request)
        saved = self.store.case(request["case_id"])
        if not saved:
            raise ValueError("找不到第一階段快照，請先 prepare")
        _, context, bundle = saved
        history = self.store.reviews(request["case_id"])
        request_hash = digest(request)
        for previous_hash, previous_request, previous_result in history:
            if previous_hash == request_hash:
                return previous_result
            if (previous_request["proposal"]["proposal_id"], previous_request["proposal"]["version"]) == (request["proposal"]["proposal_id"], request["proposal"]["version"]):
                raise ValueError("同一提案版本不可修改內容；請增加 version")
        now = self.now()
        checks = check_context(context, self.policy, now)
        if bundle["status"] != "PREPARED":
            checks.append(finding("UNPREPARED", "HUMAN_REVIEW", "HUMAN", "第一階段尚未完成，不可進入放行流程"))
        if request["constraint_bundle_id"] != bundle["constraint_bundle_id"] or request["context_hash"] != bundle["context_hash"]:
            checks.append(finding("BUNDLE_MISMATCH", "NEEDS_DATA", "STRATEGY", "必須引用本案件的完整快照與限制包"))
        if digest(self.policy) != bundle["policy_hash"]:
            checks.append(finding("POLICY_CHANGED", "HUMAN_REVIEW", "HUMAN", "政策內容已改變；請重新準備新案件"))
        if parse_time(now) > parse_time(bundle["valid_until"]):
            checks.append(finding("BUNDLE_EXPIRED", "NEEDS_DATA", "ERP_FX", "限制包已過期，需重新取得資料並準備新案件"))
        if request["proposal"]["market_snapshot_id"] != context["market"]["snapshot_id"]:
            checks.append(finding("MARKET_MISMATCH", "NEEDS_DATA", "FX", "提案與快照使用不同市場資料"))
        if history and (history[-1][2]["decision"] != "REVISE" or request["proposal"]["version"] <= history[-1][1]["proposal"]["version"]):
            checks.append(finding("CASE_STATE", "HUMAN_REVIEW", "HUMAN", "本案件已終止或版本未遞增，需建立新案件"))
        checks.extend(check_proposal(context, request["proposal"], self.policy))
        scenarios = []
        # Do not emit misleading stress results when direction/currency/maturity is invalid.
        if not any(c["status"] in {"NEEDS_DATA", "HUMAN_REVIEW"} or c["code"] in {"HEDGE_MATCH", "DUPLICATE_TRADE"} for c in checks):
            stress_check, scenarios = stress_test(context, request["proposal"], self.policy)
            checks.append(stress_check)
        attempt = len(history) + 1
        statuses = {c["status"] for c in checks}
        decision = "HUMAN_REVIEW" if "HUMAN_REVIEW" in statuses else "NEEDS_DATA" if "NEEDS_DATA" in statuses else "REVISE" if "REVISE" in statuses else "APPROVE"
        if decision == "REVISE" and attempt >= self.policy["max_review_attempts"]:
            decision = "HUMAN_REVIEW"
            checks.append(finding("RETRY_LIMIT", "HUMAN_REVIEW", "HUMAN", "已達審查次數上限，禁止繼續自動重算"))
        response = {
            "schema_version": "1.0", "case_id": request["case_id"],
            "proposal_id": request["proposal"]["proposal_id"], "proposal_version": request["proposal"]["version"],
            "proposal_hash": digest(request["proposal"]), "constraint_bundle_id": bundle["constraint_bundle_id"],
            "policy_version": bundle["policy_version"], "evaluated_at": now,
            "decision": decision, "review_attempt": attempt,
            "approval_scope": "DEMO_POLICY_ONLY", "execution_allowed": False,
            "checks": checks, "stress_scenarios": scenarios, "external_reviews": self.external_reviews(),
            "next_action": {"APPROVE": "DEMO_COMPLETE", "REVISE": "REOPTIMIZE", "NEEDS_DATA": "REFRESH_CONTEXT", "HUMAN_REVIEW": "ESCALATE"}[decision],
        }
        validate("phase2_output", response)
        self.store.save_review(request_hash, request, response)
        return response
