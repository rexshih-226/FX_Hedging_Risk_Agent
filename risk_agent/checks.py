"""Deterministic tools. No LLM-generated numbers or legal conclusions."""
from datetime import date
from decimal import Decimal

from .contracts import parse_time


def number(value):
    return Decimal(str(value))


def finding(code, status, owner, message, actual=None, limit=None):
    return {"code": code, "status": status, "owner": owner, "message": message, "actual": actual, "limit": limit}


def check_context(request, policy, evaluated_at):
    checks = []
    exposure, market = request["exposure"], request["market"]
    now = parse_time(evaluated_at)
    age = (now - parse_time(market["as_of"])).total_seconds()
    if age < 0 or age > policy["max_market_age_seconds"]:
        checks.append(finding("MARKET_TIME", "NEEDS_DATA", "FX", "報價過期或位於審查時間之後", age, policy["max_market_age_seconds"]))
    if (now - parse_time(request["as_of"])).total_seconds() < 0:
        checks.append(finding("CONTEXT_TIME", "NEEDS_DATA", "ERP", "案件資料時間位於審查時間之後"))
    if (now - parse_time(request["as_of"])).total_seconds() > policy["max_context_age_seconds"]:
        checks.append(finding("CONTEXT_STALE", "NEEDS_DATA", "ERP", "曝險與既有部位快照過期，需重新準備案件"))
    if date.fromisoformat(exposure["maturity_date"]) <= now.date():
        checks.append(finding("MATURITY", "NEEDS_DATA", "ERP", "曝險到期日必須晚於審查日期"))
    entity = request["entity"]
    if request["mode"] != "DEMO" or entity["jurisdiction"] != "US" or entity["tax_residency"] != "US" or entity["functional_currency"] != "USD" or entity["accounting_basis"] != "US_GAAP":
        checks.append(finding("UNSUPPORTED_SCOPE", "HUMAN_REVIEW", "HUMAN", "本版只實作美國、USD 功能幣、US GAAP 的模擬案例"))
    if request["counterparty"]["jurisdiction"] != "US":
        checks.append(finding("CROSS_BORDER", "HUMAN_REVIEW", "HUMAN", "跨境交易需額外適用性確認，本版不作自動法律判斷"))
    if market["base_currency"] != exposure["currency"] or market["quote_currency"] != "USD" or exposure["currency"] == "USD":
        checks.append(finding("QUOTE_CONVENTION", "NEEDS_DATA", "FX", "需要 USD / 一單位曝險外幣的直接報價"))
    ids = [h["trade_id"] for h in request["existing_hedges"]]
    if len(ids) != len(set(ids)):
        checks.append(finding("DUPLICATE_EXISTING", "NEEDS_DATA", "ERP", "既有合約 ID 重複"))
    direction = "BUY_BASE" if exposure["exposure_amount"] < 0 else "SELL_BASE"
    for hedge in request["existing_hedges"]:
        if hedge["currency"] != exposure["currency"] or hedge["maturity_date"] != exposure["maturity_date"] or hedge["direction"] != direction:
            checks.append(finding("EXISTING_SCOPE", "HUMAN_REVIEW", "HUMAN", "既有合約需同幣別、同到期日且對應曝險方向；其他情況需擴充模型"))
    if not (policy["effective_from"] <= now.date().isoformat() < policy["effective_to"]):
        checks.append(finding("POLICY_DATE", "HUMAN_REVIEW", "HUMAN", "政策不在生效區間"))
    return checks


def check_proposal(context, proposal, policy):
    checks = []
    exposure = context["exposure"]
    expected = "BUY_BASE" if exposure["exposure_amount"] < 0 else "SELL_BASE"
    legs = proposal["legs"]
    for leg in legs:
        if leg["currency"] != exposure["currency"] or leg["maturity_date"] != exposure["maturity_date"] or leg["direction"] != expected:
            checks.append(finding("HEDGE_MATCH", "REVISE", "STRATEGY", "新增合約幣別、到期日或方向不匹配"))
    ids = [x["trade_id"] for x in legs]
    existing_ids = {x["trade_id"] for x in context["existing_hedges"]}
    if len(ids) != len(set(ids)) or existing_ids.intersection(ids):
        checks.append(finding("DUPLICATE_TRADE", "REVISE", "STRATEGY", "新增合約 ID 重複或與既有合約相同"))
    existing = sum((number(x["notional"]) for x in context["existing_hedges"]), Decimal(0))
    new = sum((number(x["notional"]) for x in legs), Decimal(0))
    ratio = (existing + new) / abs(number(exposure["exposure_amount"]))
    if ratio > number(policy["max_hedge_ratio"]):
        checks.append(finding("MAX_HEDGE_RATIO", "REVISE", "STRATEGY", "既有與新增合約合計超過名目本金避險上限", float(ratio), policy["max_hedge_ratio"]))
    else:
        checks.append(finding("MAX_HEDGE_RATIO", "PASS", "RISK", "名目本金避險比例通過", float(ratio), policy["max_hedge_ratio"]))
    return checks


def stress_test(context, proposal, policy):
    """Terminal loss relative to unhedged spot-reference cash flow; USD, no discounting.

    Exposure E is signed foreign-currency cash flow. BUY_BASE forward terminal P&L
    is N*(S-K); SELL_BASE is N*(K-S). Fees are charged once. Not VaR or MTM.
    """
    spot = number(context["market"]["spot"])
    amount = number(context["exposure"]["exposure_amount"])
    legs = context["existing_hedges"] + proposal["legs"]
    fees = sum((number(x["fee_usd"]) for x in legs), Decimal(0))
    scenarios = []
    for shock in policy["spot_shocks"]:
        stressed = spot * (1 + number(shock))
        exposure_pnl = amount * (stressed - spot)
        hedge_pnl = sum((number(x["notional"]) * (stressed - number(x["forward_rate"])) * (1 if x["direction"] == "BUY_BASE" else -1) for x in legs), Decimal(0))
        pnl = exposure_pnl + hedge_pnl - fees
        loss = max(-pnl, Decimal(0))
        scenarios.append({"shock": shock, "spot": float(stressed), "exposure_pnl_usd": float(exposure_pnl), "hedge_pnl_usd": float(hedge_pnl), "fees_usd": float(fees), "loss_usd": float(loss)})
    worst = max(x["loss_usd"] for x in scenarios)
    passed = number(worst) <= number(policy["max_stress_loss_usd"])
    check = finding("STRESS_LOSS", "PASS" if passed else "REVISE", "RISK" if passed else "STRATEGY", "到期情境損失檢查；非 VaR，未計折現或期間保證金", worst, policy["max_stress_loss_usd"])
    return check, scenarios
