# 給其他組員的串接摘要

請先閱讀 `interfaces.md`，交付時將整個 `schemas/` 一起提供：主要 Schema 會引用 common.json，不能只複製單一檔案。

| 對象 | 需要提供給 Risk | Risk 回傳 |
|---|---|---|
| ERP Agent | 一筆外幣淨曝險、到期日、用途、快照時間、既有合約明細 | 缺件原因與 owner=ERP |
| FX Agent | 報價方向、spot、報價時間、snapshot_id | 過期／報價方向錯誤與 owner=FX |
| Strategy Agent | 同一限制包下的新合約清單、完整遠期匯率、費用、提案版本 | 限制包；通過／退回及 actual、limit、原因 |
| Orchestrator | case_id、法人與預設交易銀行背景，串行觸發兩階段 | next_action；需處理重算與補件路由 |
| Execution Agent | 未來接收正式核准提案；本版不可執行 | execution_allowed=false；禁止以 DEMO_POLICY_ONLY 核准送銀行 |

第一階段輸入的法人與交易銀行資訊由案例／整合層組裝，不要求 ERP 自行推測。初版銀行預先指定；若 Strategy 更換銀行，應建立新案件重新判斷適用規則。

外匯選擇權、NDF、不同到期日淨額沖抵、跨境法律適用、正式申報責任、稅務／會計文件、制裁篩查不在已實作範圍。下一版需先協調這些欄位，再擴充工具，不能只增加 product 字串就認定支援。

模擬損失上限 USD 80,000、比例 80%、spot=1.1 皆為教學設定。其他 Agent 應明確顯示 simulation，避免當成 NVIDIA 真實政策與市場資料。
