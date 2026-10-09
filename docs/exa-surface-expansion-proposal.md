# Exa 進階取用面擴充提案

狀態：Proposal（未實作）
對象：`scripts/reach.py` 與 `references/deep-dispatch.md` 的搜尋／讀取通道
前置：6.4.8 已讓 keyed 模式可驗證（見該版 devlog）。本提案假設金鑰已接線。

## 1. 為什麼現在談

6.5.2 修的是「有金鑰卻沒用上」。接下來的问题是：**接上了，然後呢？**

現行 `reach.py` 走 `mcporter` → Exa 官方 hosted MCP，只用兩個工具：

| 工具 | 用途 | 現行是否使用 |
|---|---|---|
| `web_search_exa` | 一般語意搜尋，回 title/url/highlights | 是（`search`）|
| `web_fetch_exa` | 讀已知網址的乾淨內容，預設 3000 字 | **否**（讀頁一律走 Jina Reader）|
| `web_search_advanced_exa` | 進階過濾：category／domain／日期區間／text 約束／geo／query expansion／summary／highlights／`maxAgeHours`／子頁抓取 | 否（需 opt-in）|
| `agent_run` | 多步研究、列名單、enrichment、結構化輸出 | 否（需 OAuth 或金鑰）|

後兩項是 keyed 之後才出現的（免鑰連 `agent_run` 都不會列在工具表裡）。目前它們等於不存在。

### 現行的結構性短板

1. **抓頁不用 Exa**。`reach.py read` 走 Jina Reader，好處是免 key、20000 字；代價是多一個外部依賴與 20 RPM 上限。`web_fetch_exa` 是同類能力的第二後路，Jina 掛掉時可以退。
2. **無法逐欄抽取**。合規／盡調要的是「每個對象的牌照號、監管機關、狀態、日期」，現在只能拿 highlights 全文回主 session 自己 parse。`agent_run` 的 `outputSchema` 可以在**服務端**做這件事。
3. **無法列名單**。vendor-DD 的「找出所有持牌機構並逐家查」需要多步研究與逐項過濾，現行只能靠第二輪通道 A/B 人工拆格補。

## 2. web_search_advanced_exa

官方定位：一般搜尋維持 `web_search_exa`（工具面小、免設定）；需要明確過濾／日期／摘要／freshness 才用 advanced。advanced **不要求認證**，但已認證的連線走自己的方案與額度。

啟用方式是把工具清單寫進 URL（**顯式清單會取代預設，所以要含回 `web_search_exa`**）：

```text
https://mcp.exa.ai/mcp?tools=web_search_exa,web_fetch_exa,web_search_advanced_exa,agent_run
```

### 提案：不做預設開啟

`?tools=` 一旦寫死，所有 session 的工具面都變大，模型在不需要時也可能去選 advanced。與 `search` 的定位（「唯一入口」，克制、少設定）衝突。

**提案做法**：`reach.py search` 維持只用 `web_search_exa`；需要進階過濾時走新旗標，由任務條件決定，而非預設：

| 旗標 | 對應 advanced 欄位 | 適用情境 |
|---|---|---|
| `--since <YYYY-MM-DD>` / `--until` | `startPublishedDate` / `endPublishedDate` | 題目明講 bounded window（「2026 年內」「最近七個月」）|
| `--domain <d>`（可重複）| `includeDomains` | 使用者指定硬 allowlist |
| `--summary` | `summary` | 題目要求逐筆摘要 |
| `--fresh <hours>` | `maxAgeHours` | 抓取內容必須是新的（爬取快取上限，**不是**出版日期篩選）|

### 必須寫進 references 的兩條誤用防線

1. **`maxAgeHours` 不是「最新」控制項**。它管的是抓取內容的快取新舊。要「最近的消息」應寫在 query 字面（`latest`、`recent`）。誤用會得到「頁面很新但內容是舊聞」或反之。
2. **日期區間是硬篩選，會丟掉沒標日期與日期錯誤的頁**。只在題目明講必須 enforce 的窗口才用；「最新」這種模糊需求用了就會漏。

## 3. agent_run

官方定位：需要多次搜尋才完成的研究——建清單、逐項比對條件、回傳結構化結果。走金鑰或 OAuth 時預設開啟。

可選欄位：`systemPrompt`（研究判準）、`outputSchema`（固定 JSON）、`input.data`（補齊手上已有筆目）、`input.exclusion`（略過已知結果）、`dataSources`（最多五個 Exa Connect 來源）、`previousRunId`（對已完成研究追問）、`effort`（研究深度）。

非同步：單次呼叫跑不完**不算失敗**，工具回 `status: "running"` 帶 `id`，再帶 `runId` 呼叫同一輪可接回。

### 對應到現有三個痛點

| 現況痛點 | agent_run 對應欄位 | 省下什麼 |
|---|---|---|
| 逐欄抽取靠主 session parse highlights | `outputSchema` | 服務端抽欄位；主 session 只收已驗證的 JSON |
| 「找出所有持牌機構並逐家查」人工拆格 | `query` + `effort` + `dataSources` | 一輪內多步完成，不吃 ledger 的 fetch 額度 |
| 第二輪通道 A「換角度」靠重新組 query | `previousRunId` | 對同一批結果追問，不重付搜尋成本 |

### 提案：`reach.py agent` 子命令的形狀

```bash
reach.py agent "<目標>" --cell <格> [--schema <json|@file>] [--system <檔>] \
                     [--effort low|medium|high] [--poll <秒>] [--timeout <秒>]
```

實作注意事項（照 `reach.py` 既有形狀對齊）：

1. **先扣 `budget.py`**。`agent` 不是單次搜尋，但必須在發請求前先記一筆，否則 ledger 會出現沒有對應花費的查詢。建議記 `r2a_*`（與 `reach.py` 的 `r2_*`、`camofox_fetch.py` 的 `r2c_*` 併行不搶額度）。
2. **輪詢要落檔**。`status: "running"` 時的 `id` 要寫進 ledger 旁的 `.research-deep/`，中斷後可接回；否則 deep 執行人中途被回收就整輪蒸發。
3. **超時要退款**。與 `search` 的 429 退避、ddgs 備援同一套語意：兩者（deep 端有輸出、sandbox 端有）都失敗才 refund。
4. **不要自動降級到 ddgs**。`agent_run` 沒有等價的備援；失敗就報失敗，讓人決定是否退回 `search` 通道。靜默換通道會讓報告以為拿到了結構化結果。
5. **成本要出聲**。agent 走用量計費。`--effort` 預設 `medium`，且在 devlog 記錄實測單輪花費。

### 為什麼走 MCP 而不直打 `api.exa.ai/agent`

兩者功能重疊，但 MCP 已經是本 repo 的既有通道（`reach.py` 全部搜尋都經 `mcporter`），且 agent 的欄位在 MCP 側已齊（`query` / `runId` / `systemPrompt` / `outputSchema` / `input`）。直打 `/agent` 會多一份要自己維護的輪詢與重試邏輯，還得自己處理非同步 run 的續接。**只有在 MCP 的欄位不夠用時才值得升級到直打。**

## 4. Monitors：仍須直打 API

MCP **不提供** Monitors。要定期盯監管機關公告、制裁名單變動、牌照名冊改版，只能直打 `api.exa.ai/monitors`。

### 適配性評估

| 面向 | 評估 |
|---|---|
| 與本 repo 流程的關係 | **正交**。`vera-research` 是一次性研究（選模式 → 補齊矩陣 → 停損出稿），Monitors 是長期排程觀測。塞進 `references/deep-dispatch.md` 會混淆「這一輪怎麼查」與「每週怎麼看」|
| 成本 | Monitors 與 Websets **不是 ZDR**（`/search`、`/answer`、`/agent` 才是）。合規調研若涉敏感標的，資料留存是必須先確認的條件 |
| 交付 | 走 webhook。本 repo 沒有 webhook 接收端，要另拉一條通知鏈（Machine 層能力，不屬 skill 範圍）|
| 實質收益 | 中。FATF 灰名單、FCA/SFC 處分名冊這類變動，現行靠 `registry-directories.md` 的名冊 URL＋人工重查已能覆蓋；Monitors 省的只是「記得去看」|

### 提案：**不做**，但保留記錄

理由是收益不足以支撐新增的 webhook 基礎設施與 ZDR 帶來的合規確認成本。若日後出現「同一題目每週都要重跑」的實證需求（例如追蹤某組對手的牌照／訴訟變動），再以獨立提案重開，不要先在 deep-dispatch 埋伏筆。

## 5. Snapshot：適配性中等，同樣先不做

`/contents` 與 `/search` 都有 `snapshotAsOf`，可取回某個過去時點的頁面版本。MCP 側**不提供**。

### 實質價值

合規報告常有一句「該監管頁在資料截止日載明 X」。現在這句話的舉證方式是「我們在 T 日抓過」——證據是抓取當下的頁面，之後頁面一改就無法回溯。Snapshot 能把「T 日的頁面」變成可重新取得的物件。

具體到本 repo 的三個位置：

1. **`evidence-standards.md` 的逐字摘錄核實**。現在要求摘錄出現在落檔正文中；頁面若在落檔後被改寫，覆核會失敗。Snapshot 可讓覆核用同一時點重取。
2. **監管頁面的時點引用**（FATF 聲明、名冊版本）。名冊尤其需要：名冊會更新，報告引用的是哪一版是實質爭點。
3. **政策頁對比**（政策前後差異）。

### 提案：**不做**，理由

- 快照只保留有限時間窗與數量（官方有 `limits`），不是永久存證；真要當存證仍得自己存雜湊與時間戳。
- 改動會碰到 `budget.py` 記帳語意（snapshot 是 fetch 還是獨立種類），以及 `validate_report.py` 的 URL 存活檢查（快照 URL 的狀態碼語意不同）。這兩處動到的是核心預算與驗收路徑，風險遠高於收益。
- 真正的解法可能不是 Snapshot：把落檔正文連同 `sha1` 與抓取時間寫進 ledger 就夠了，成本近乎零。**先量測「覆核失敗有多少是因為頁面事後被改」**，有實證再談 Snapshot。

## 6. agent-reach 的文件已過時

`~/.claude/skills/agent-reach/references/search.md` 只列兩個工具（`web_search_exa`、`get_code_context_exa`），並宣稱 Exa「**無需 API key**」。兩個問題：

1. `get_code_context_exa` 在現行 Exa MCP 工具表裡**已不存在**（現行是 `web_fetch_exa`）。指令照抄會直接失敗。
2. 加金鑰後 `agent_run` 會出現，「無需 API key」這句會讓人錯判能力邊界。

該 skill 由上游 `Panniantong/Agent-Reach` 維護，本地副本改了會被同步覆蓋。**提案**：先在本 repo 的 `references/deep-dispatch.md` 記錄實際工具表與認證三態（keyless／OAuth／`x-api-key`），讓本 repo 的操作不受上游文件滯後影響；上游修正另循 PR 路線，不在本 PR 範圍。

## 7. 建議順序

| 優先 | 項目 | 理由 |
|---|---|---|
| 1 | §2 `web_search_advanced_exa` 的按需旗標 | 成本最低、防線明確（兩條誤用規則），且不需要非同步輪詢 |
| 2 | §6 在 `references/deep-dispatch.md` 記錄實際工具表 | 純文件，先讓現況不再誤導 |
| 3 | §3 `reach.py agent` | 收益最大但工程量與測試面也最大（輪詢、落檔、退款、成本記錄）；建議獨立 PR |
| — | §4 Monitors、§5 Snapshot | 提案不做，附不做理由與重啟條件 |

每項獨立 PR，各自附測試與 devlog。本提案本身不含可執行程式碼。
