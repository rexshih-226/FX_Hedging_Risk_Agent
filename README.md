# NVIDIA 案例：Risk Agent 基礎架構

以 NVIDIA 為背景的企業外匯避險風控原型。公司帳務、交易、80% 上限及損失限額皆為**作業模擬資料**，不是 NVIDIA 的內部政策或真實部位。

本版完成：兩階段 JSON Schema、可執行的確定性審查流程、SQLite 案件與版本紀錄、官方資源目錄、原始資料匯入入口、文件檢索入口及測試。**LLM、自動法律適用性判讀、選擇權定價、正式制裁篩查、銀行 API 尚未接入。**這是完整 Agent 的基礎骨架，不宣稱已完成自主法遵 Agent。

## 執行

Python 3.11+；在此目錄執行：

```powershell
python -m pip install -r requirements.txt
python -m risk_agent demo
python -m unittest discover -s tests -v
```

demo 輸出至 `artifacts/demo/`，重跑會建立新的案件 ID，不清除舊紀錄。

```powershell
python -m risk_agent prepare --input examples/phase1_input.json --db artifacts/manual.sqlite --at 2026-11-23T02:01:00Z
python -m risk_agent review --input examples/phase2_input.json --db artifacts/manual.sqlite --at 2026-11-23T02:01:00Z
python -m risk_agent review --input examples/phase2_corrected_input.json --db artifacts/manual.sqlite --at 2026-11-23T02:01:00Z
python -m risk_agent fetch sec_submissions --user-agent "UniversityRiskProject contact@example.edu"
```

最後一個指令是選用的外部唯讀請求；請換成真實聯絡資訊。資料只進入原始快照，不會自動變成正式規則。網路被封鎖時會回報失敗，不會用模型記憶補造資料。

以上 --at 是模擬評估時鐘；省略時使用執行當下時間，舊範例可能因資料過期而要求補件。修改範例內容時，第二階段必須改用新 prepare 回傳的 constraint_bundle_id 與 context_hash。修改 Schema 生成器後依序執行 `python scripts/build_contracts.py`、`python scripts/build_examples.py`，以保持範例雜湊一致。

## 導覽

| 檔案／目錄 | 內容 |
|---|---|
| `docs/architecture.md` | 模組邊界、資料流程、系統流程、Agent 接入位置 |
| `docs/interfaces.md` | 兩階段四種輸入／輸出、欄位語意與決策狀態 |
| `docs/resources.md` | 官方資源、取得方式、適用性與接入進度 |
| `schemas/` | JSON Schema Draft 2020-12；可交給其他組員 |
| `examples/` | 模擬政策、第一階段輸入、四種輸入／輸出範例 |
| `config/sources.json` | 機器可讀的線上資料來源目錄 |
| `risk_agent/` | 控制層、檢查工具、儲存、匯入與檢索入口 |
| `tests/` | 放行、超限、過期、版本、重試與資料錯誤測試 |
| `artifacts/demo/` | 本次執行的真實輸出與 SQLite 紀錄 |

## 本版範圍

- 一個美國非金融企業模擬法人、一筆非 USD 曝險、USD 報價、同到期日的實物交割遠期。
- 正號為外幣應收，負號為外幣應付；金額均以曝險外幣計價。
- `spot`、`forward_rate` 是 **USD / 一單位曝險外幣**，不接受反向報價自動猜測。
- 壓力測試使用原始曝險＋既有遠期＋新增遠期，計算到期損益；這不是 VaR。
- 規則在第一階段固定成具雜湊的快照，第二階段重新驗證時效與版本。
- 即使範例得到 `APPROVE`，也僅代表 `DEMO_POLICY_ONLY`；`execution_allowed` 永遠為 `false`。法規、稅務、會計與制裁尚未完成時，不會產生實盤核准。

欲支援選擇權，應新增商品 schema、到期／存續期間定價與風險計算工具，並明定名目本金或 Delta 比例口徑；不能沿用本版遠期公式。
