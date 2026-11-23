# 線上資源與接入清單

整理日期：2026-11-23（Asia/Taipei）。本表是資料來源登錄與研究計畫，不是對 NVIDIA 任一真實交易的法律結論。機器可讀版本：`config/sources.json`。

「入口確認」表示官方網站或官方文件能被網頁工具辨識；不代表端點已從本機串接、所有版本均已下載或資料已涵蓋全部義務。

## 美國與公司資訊

| ID | 官方資源 | 使用方式 | 本版狀態 |
|---|---|---|---|
| sec_submissions | [SEC API 文件](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)；[NVIDIA 索引 JSON](https://data.sec.gov/submissions/CIK0001045810.json) | 取得 CIK 0001045810 的申報索引；再下載特定 10-K／10-Q 文件。索引不是 ERP 明細 | JSON 已由網頁工具讀取；本地下載器已實作，尚未以使用者真實 User-Agent 進行線上整合測試 |
| nvidia_ir | [NVIDIA Financial Reports](https://investor.nvidia.com/financial-info/financial-reports/default.aspx) | 選定財報版本，研究外匯風險、衍生品附註與會計政策 | 官方入口已確認；尚未自動解析 |
| federal_register | [Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1) | 發現公告與修法，保留文件類型、生效資訊及官方版本連結 | 文件入口確認；尚未接 API |
| ecfr | [eCFR API](https://www.ecfr.gov/developers/documentation/api/v1) | 取得法規文本與版本資訊；確認日期及資料性質 | 文件入口確認；尚未接 API |
| cftc | [CFTC FX 商品處理參考函件](https://www.cftc.gov/csl/25-10/download) | 研究實物交割遠期、換匯、NDF 與選擇權的分類差異，再回查法規依據 | 官方文件已找到；不是完整規則庫，未實作適用性引擎 |
| ofac | [OFAC Sanctions List Service](https://ofac.treasury.gov/sanctions-list-service) | 取得結構化制裁名單；後續加入實體辨識、適用方案與持有關係檢查 | 入口確認；下載／篩查尚未接入 |
| tax_cfr | [官方 2025 年版 26 CFR 1.1221-2](https://www.govinfo.gov/content/pkg/CFR-2025-title26-vol13/xhtml/CFR-2025-title26-vol13-sec1-1221-2.html) | 研究避險辨識與紀錄要求；先確認交易稅務分類及現行版本 | 歷史版本已找到；未實作，不能直接將此條全部套到 FX |
| irs | [IRS Internal Revenue Bulletin](https://www.irs.gov/irb) | 追蹤正式稅務公告；依選定議題解析 | 官方入口確認；未接入 |
| fasb | [FASB Standards](https://www.fasb.org/standards)；[Codification](https://asc.fasb.org/) | 研究 US GAAP／ASC 815 及相關規範，保留具體段落與版本 | 來源確認；需依存取條款人工或授權匯入，未建立全文 API |

SEC 的公開資料 API 與 EDGAR 申報提交 API 是不同服務。此專案只讀取公開資料，無申報或交易權限。下載前依 [SEC Developer Resources](https://www.sec.gov/about/developer-resources) 設定識別資訊與存取節奏。

## 國際／海外

| ID | 官方資源 | 使用方式 | 邊界 |
|---|---|---|---|
| esma_emir | [ESMA EMIR Reporting](https://www.esma.europa.eu/data-reporting/emir-reporting) | 涉及歐盟法人、對手或其他跨境條件時，評估義務與責任分配 | 未實作；EUR 幣別本身不是觸發依據 |
| fx_global_code | [FX Global Code](https://www.newyorkfed.org/fxc/fx-global-code) | 將相關治理、交易與交割實務納入公司控制設計 | 本身不創設法律或監理義務；不可標記為全球強制法 |

其他地區（例如英國、新加坡、臺灣）先作人工適用性觸發。確認案例真的包含該地法人或相關交易條件後，再加入當地主管機關資料；本版未宣稱覆蓋所有海外地區。

## 匯入與規則生命週期

```text
官方 API / 頁面 / 文件
  → 原始快照：source_id、URL、抓取時間、SHA-256、檔案位置
  → 解析與候選條件：條號、範圍、發布日、生效日、例外、證據段落
  → 適用性及內容確認
  → 正式版本
  → 第一階段限制／第二階段檢查
```

此版只有第一個來源下載入口及原始快照存檔已實作。候選擷取、核准介面、正式法律規則發布、定時更新均待接入；不可將下載成功標記成法律審查通過。

來源衝突或未知時保留原文及歧義，轉人工覆核。不要只依 LLM 信心分數啟用規則。稅務例子尤其要注意 §1.1221-2 與 section 988 的協調條款，不能把前者的辨識時限寫成全部外匯交易的通則。

## RAG 實作順序

1. 先用小量文件與關鍵字檢索。`LocalTextRetriever` 是獨立工具入口，不會自動影響審查。
2. 再加入條文切分及 metadata：jurisdiction、entity_scope、product_scope、effective_from/to、status、source_id、section、version。
3. 擴充向量與關鍵字混合檢索，保留定義、例外與交叉引用；不同語言亦需對應。
4. 讓 LLM 以證據生成解釋或候選規則；最終數值限制由已確認規則庫供應。

RAG 可採關鍵字、語意、向量或混合索引，不必一開始建向量庫。[Microsoft 官方 RAG 文件](https://learn.microsoft.com/en-us/azure/foundry/concepts/retrieval-augmented-generation?view=foundry-classic)

## 更新節奏（專案建議，不是法定頻率）

- 公司申報索引、Federal Register、eCFR：每日或展示時手動更新。
- 模擬內規：核准變更後發布新版本，不覆寫舊版本。
- 制裁資料：執行前及名單更新時重新確認；正式頻率由合規設計決定。
- 會計與海外要求：有新版本或案件範圍變更時檢查。

目前沒有建立自動排程；來源刷新失敗不得用模型記憶補造，應記錄錯誤、資料時間與待處理狀態。
