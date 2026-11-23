# 兩階段基本介面 v1.0

時間用含時區的 ISO 8601；日期為 YYYY-MM-DD。正金額為應收，負金額為應付。貨幣代碼用三碼大寫。此版是一筆曝險一個案件，已知欄位以外的內容會拒絕。多法人、多幣別、多到期區間需另建批次封套，不能混加。

## 第一階段：Risk → Strategy 的事前限制

輸入 Schema：`schemas/phase1_input.json`；範例：`examples/phase1_input.json`。

| 欄位 | 提供者 | 意義 |
|---|---|---|
| schema_version、case_id、mode | Orchestrator | 格式版本、不可變案件 ID；只有 DEMO 能完成模擬核准 |
| as_of | ERP／整合層 | 曝險與既有部位快照時間，不是 Agent 的評估時間 |
| entity | 案例設定／ERP | 法人、地區、稅務居民、功能幣與會計框架 |
| counterparty | Strategy／交易設定 | 銀行、司法管轄區與簽約分支機構 |
| exposure | ERP | exposure_id、currency、exposure_amount、maturity_date、purpose |
| existing_hedges | ERP／交易庫 | 明確列出既有合約；空陣列表示確認無既有合約，不是未知 |
| market | FX | snapshot_id、as_of、base_currency、quote_currency、spot |

使用 maturity_date 作為主欄位，以免 days_to_maturity 隨日期改變。組員原本的天數格式可在整合層依明確基準日轉為到期日；不要同時傳兩個互相矛盾的值。

輸出 Schema：`schemas/phase1_output.json`；範例：`examples/phase1_output.json`。

| 欄位 | 意義 |
|---|---|
| status | PREPARED／NEEDS_DATA／HUMAN_REVIEW；只有 PREPARED 可求解 |
| constraint_bundle_id、context_hash | 綁定曝險、既有合約、市場、交易背景與政策 |
| policy_version、policy_hash | 對應 SQLite 保存的完整模擬政策 |
| created_at、valid_until | 審查時鐘與最早到期界線，不是市場報價時間 |
| constraints | 比例上限、既有金額、最大新增金額、商品、方向、到期日、壓力測試條件 |
| checks | 資料問題、負責補正單位與原因 |
| external_reviews | 尚未實作的法律、制裁、稅務、會計、跨境領域，不能解讀成通過 |
| approval_scope、execution_allowed | 此版固定 DEMO_POLICY_ONLY／false |

Strategy 應將 max_new_notional 直接寫入限制式，但仍需在相同情境與定價口徑下處理 max_stress_loss_usd；不能只遵守 80% 上限而忽略風險下限。

## 第二階段：Strategy → Risk 的提案審查

輸入 Schema：`schemas/phase2_input.json`；範例：`examples/phase2_input.json`。

| 欄位 | 意義 |
|---|---|
| case_id、constraint_bundle_id、context_hash | 必須原樣引用第一階段回傳的值 |
| proposal.proposal_id、version | 提案身分；內容改動必須增加版本 |
| proposal.market_snapshot_id | 必須引用相同市場快照；更新報價需重新 prepare |
| proposal.legs | 新增合約，不包含既有合約，避免重複計算 |

本版合約格式：

```json
{
  "trade_id": "NEW-001",
  "product": "deliverable_forward",
  "currency": "EUR",
  "direction": "BUY_BASE",
  "notional": 1500000,
  "maturity_date": "2027-01-22",
  "forward_rate": 1.1,
  "fee_usd": 1000
}
```

BUY_BASE 為買入曝險外幣、賣 USD；SELL_BASE 相反。notional 一律正數。forward_rate 為完整遠期匯率，不是遠期點數；FX／Strategy 負責先確認點數單位後換算。空 legs 合法，但仍需符合壓力損失限額。

輸出 Schema：`schemas/phase2_output.json`；範例：`examples/phase2_output.json` 與 `examples/phase2_revise.json`。

| decision | next_action | 誰接手 |
|---|---|---|
| APPROVE | DEMO_COMPLETE | 本版僅模擬結束；不交銀行 |
| REVISE | REOPTIMIZE | Strategy；依 checks 修正並提高 version |
| NEEDS_DATA | REFRESH_CONTEXT | 依 checks.owner 找 ERP／FX／整合層補資料，重建案件 |
| HUMAN_REVIEW | ESCALATE | 人工確認適用性、規則衝突或重試耗盡 |

輸出含 proposal_hash、審查時間、規則版本、每項檢查的 actual／limit、情境分解與伺服器端 review_attempt。風險數值由工具重算，不使用 Strategy 自報的「已合規」。

## 計算契約

- 全部風險金額以 USD 表示；曝險及名目本金以曝險外幣表示。
- 比例分母為該案件淨曝險絕對值；分子為同幣別、同到期日、相同避險方向的既有＋新增名目本金。
- 壓力情境固定 spot ±10%，不是機率預測，也不是 VaR。
- 定義 E 為有正負號的曝險、S0 為 spot、S 為壓力匯率、N 為遠期名目本金、K 為遠期成交匯率：
  - 原始曝險增量損益：E × (S − S0)。
  - BUY_BASE 遠期損益：N × (S − K)；SELL_BASE：N × (K − S)。
  - 合計損益扣掉既有及新增合約列入的 fee_usd；損失為 max(−合計損益, 0)。
- 這是相對 S0 的到期現金流情境，未折現、未評估中途保證金與違約風險。既有已支付費用若不應算入本次指標，輸入應按小組約定填 0；不能未經約定混用費用口徑。
- 未支援的選擇權／NDF 由 schema 拒絕；不能用遠期公式替代。

## 後續可增加但目前不強制的背景

LEI、集團與持有關係、交易對手分類、交易場所、申報責任分配、避險會計指定、稅務辨識證據、保證金與現金餘額等。正式適用性引擎需將這些改成按情境必填，不能直接用本版欄位宣稱已完成法遵。
