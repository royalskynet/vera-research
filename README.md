# vera-research — `/research` router + deep-research engine

v6.0.0 把 `/research` 升級為第一層保守判斷器：依任務性質路由 `agent-reach`、`last30days`、`qmd`、`user-research`，並用原 Vera 三輪流程作原生 deep core。只有明確窄查詢走 quick；模糊任務至少 verified，低信心升一級；競品預設 decision assurance，第三方廠商背調／盡調預設 audit assurance。

原本加密交易所風控研究保留為 domain profile：`competitor`、`vendor-dd`、`academic`。命中時仍用覆蓋矩陣、預算停損、雙通道補洞、反方稽核與**簡體中文**正式報告；一般研究不套用交易所名單或風控格式。

本工程以 symlink 落地本機：

```bash
ln -s /path/to/vera-research ~/.claude/skills/research
```

## Router V2

```bash
scripts/route.py "全面調研三家 KYC 供應商的能力、牌照與負面紀錄，產出背調報告" --pretty
```

輸出包含 Task Profile、`quick|verified|deep|large`、`informational|decision|audit`、能力組合、執行階段、品質閘門、缺能力 fallback、隱私／權限 gate 與 checkpoint 契約。完整規格見 `docs/research-router-v2-spec.md`。

Deep／large 可續跑並檢查產物是否過期：

```bash
scripts/route.py "<request>" --pretty > route.json
scripts/run_state.py init --route route.json --run-dir ./research-run
scripts/run_state.py checkpoint --run-dir ./research-run --phase scope-plan-coverage --verdict PASS --artifact ./scope.md
scripts/run_state.py status --run-dir ./research-run
```

## Vera 三輪核心

1. **第一輪** 選模式 → `scripts/budget.py init --mode …` 建「平台×維度」覆蓋矩陣 → 依 `questions-<mode>.md` 的必答問題與三視角補充題生成查詢 → WebSearch，回空或不足即走 agent-reach（`scripts/reach.py search` 走 Exa；WebFetch 失敗走 `reach.py read` 走 Jina）→ 每格達 `evidence-standards.md` 門檻才 `FILLED` → `budget.py status` 印 `NEXT: draft` 即停止蒐集寫初稿。每次搜尋／抓取都先記帳；預算用盡＝這一輪停手，定額加碼規則見 `references/deep-dispatch.md`。
2. **第二輪** 只處理缺口（上限依模式），每格「兩通道各恰一次」：通道 A 本地反偵測渲染（`scripts/camofox_fetch.py`，含 `--search`）；通道 B agent-reach 換角度／換語言／替代來源（reach.py 或子代理）。牌照類缺口優先下沉 `registry-directories.md` 的名冊。
3. **整合** 補強寫回原段落並充實相鄰內容，跨維度交叉一次；定稿不留任何工作階段標記；`scripts/check_report.sh <報告> --mode <m>` 檢查來源總數、字數與簡體中文；鐵律 4 逐項語意核對（不抽樣、不送第三方模型）。
4. **第三輪** 獨立子代理反方稽核（含 `self-reported-only`／`register-unchecked` 旗標），主 session 七道閘門裁決後改寫定稿。

報告產出物禁詞 SSOT 見 `references/forbidden-words.md`。

## 目錄

| 檔 | 職責 |
|---|---|
| `SKILL.md` | 角色定位與產出品質、調研模式、深度標準摘要、預算與停損、鐵律 1–4、三輪 SOP |
| `docs/research-router-v2-spec.md` | Router V2 完整契約、強度、assurance、pipeline、schema 與驗收 |
| `references/upstream-review.md` | 六個上游＋原 Vera 的 commit、授權、安全審查與採捨 |
| `references/capabilities.md` | 五種能力的單一責任、組合、可用性與 fallback |
| `references/routing-rules.md` | Task Profile、高估優先、四強度、assurance 與續跑規則 |
| `references/evidence-standards.md` | 來源分級 S1–S5（各級能／不能證明什麼）、主張處理規則、逐項語意核對、深度門檻、名冊對照寫法 |
| `references/questions-competitor.md` | competitor 六維度必答問題與每平台一手來源 |
| `references/questions-vendor-dd.md` | vendor-dd D1–D9 必答問題、三視角提問、跨維度交叉 |
| `references/registry-directories.md` | 主管機關目錄、制裁清單、公司登記、處分、法院、卡組織名錄的 URL SSOT 與 fallback 鏈 |
| `references/report-format.md` | competitor／academic 八章格式（需求背景與目標、範圍與方法、對比、深度分析、差距、建議結論、來源） |
| `references/deep-mode.md` | 深度編排：起點資產盤點、工作包（WP）拆分、工作稿、綜合主報告、定稿門檻清單 |
| `references/report-format-vendor-dd.md` | vendor-dd 八章格式（含調研範圍與方法、逐維度宣稱／核實／評述／風險等級） |
| `references/round2-merge.md` | 第二輪兩通道分派表、缺口上限、融合與充實規則、checklist |
| `references/round3-devils-advocate.md` | 反方子代理 prompt 模板、旗標、證據包 schema、七道閘門、裁決規則 |
| `references/forbidden-words.md` | 禁詞 SSOT（fenced ```text``` 供腳本擷取）＋例外 |
| `scripts/budget.py` | 覆蓋矩陣＋預算 ledger（`--mode` 預設、spend／nonew／fill／close／gaps／phase／status、`--selftest`） |
| `scripts/route.py` | 自然語言／明確 profile 的 deterministic Router V2 |
| `scripts/run_state.py` | Deep／large checkpoint、resume manifest、verdict 與 artifact hash／STALE 驗證 |
| `scripts/reach.py` | agent-reach 膠水：`search`（Exa via mcporter）、`read`（Jina Reader）；帶 `--cell` 自動記帳 |
| `scripts/camofox_fetch.py` | 走常駐 camofox-browser REST `:9377` 的渲染與反爬搜尋；帶 `--cell` 依 ledger 拒絕超額 |
| `scripts/validate_report.py` | 引用結構、`--check-list` 逐項主張→來源清單、`--check-urls` 存活、`--lang zh-hans` 繁體誤用檢查 |
| `scripts/check_report.sh` | validate_report.py ＋ 禁詞 grep ＋ `--lang` 語言檢查膠水；`--selftest` |
| `scripts/number_cites.py` | 初稿 `[D1R2]` 標籤 → 依首次出現重編 `[N]`＋產來源表；同 URL 合併、缺來源回 exit 1 |
| `references/report-format-vendor-dd-brief.md` | vendor-dd 重點版（評分總覽、主體／合規／可靠性／能力四表、調用者前提逐條核實、子維度依據），由完整版重排不重查 |
| `references/vendor-trust-score-rubric.md` | vendor-dd 信任分數（可選）：六子維度權重（20/20/20/10/20/10）、三桶（合規 40／能力 30／可靠性 30）、A+–D 五級、各子項評分區間、跨行業調整 |
| `.githooks/pre-push` | 推前自檢 |

## 前置

`scripts/reach.py` 依賴 `mcporter` CLI 呼叫 Exa（第一輪外部搜尋 fallback）。若 `which mcporter` 為空：

```bash
npm i -g mcporter
```

reach.py 會先查 `$PATH`，再回退掃 `~/.nvm/versions/node/*/bin/`、`~/.local/bin/`、`~/.npm-global/bin/`；找不到才輸出 `[reach] mcporter not found; install: npm i -g mcporter` 並回非零 exit code。nvm 切版時裝到當前 node 版本即可，不需 admin。

### 選用：接上 Exa 金鑰（放寬並發）

Exa 免鑰 MCP 有額度上限，實測 5 路並發就有 2 路撞 `HTTP 429`。有金鑰時 `reach.py` 放寬到 5 路並發。要生效需要**兩件事同時成立**：

1. 金鑰可讀：`EXA_API_KEY` 環境變數，或 `~/.config/vera-research/EXA_API_KEY.txt`（`_exa_env()` 會讀，密鑰不落 stdout）。
2. mcporter 真的會送 header——`~/.mcporter/mcporter.json` 的 `mcpServers.exa.headers` 要有 `x-api-key`：

```bash
mcporter config add exa --url https://mcp.exa.ai/mcp \
  --header 'x-api-key=${EXA_API_KEY}' --scope home
```

值寫 `${EXA_API_KEY}` 佔位（mcporter 執行時展開），設定檔不存密鑰。**只做第 1 步不會生效**：`reach.py` 讀得到金鑰卻沒 header 可送，等於仍是匿名額度。此時 `reach.py` 會在 stderr 出聲一次並維持單路，不會靜默用 5 路把額度打爆。

## 設定

不使用本機設定檔。對標名單預設為 SKILL.md「角色定位與產出品質」所列主流交易所，使用者指定時以指定為準；報告一律不署名、不含任何組織身分資訊；渲染與搜尋通道固定走 `scripts/` 內建腳本。ledger 檔 `.research-budget.json` 與 `reports/` 不入庫。

## 關聯 skill

- `agent-reach`：第一輪的 Exa／Jina／社群通道，第二輪通道 B
- `evidence-debate-audit`（已移除）：第三輪反方稽核協定的改寫來源，內容已併入 `references/round3-devils-advocate.md`
- `evidence-research-report`（已移除）：`scripts/validate_report.py`、證據政策、外洩掃描、`evals/`、`search_web.py` 的來源工程，6.3.0 已全部併入本 skill
- `last30days`：近期社群期間、聚類與互動訊號 lane
- `qmd`：本機 Markdown 檢索 lane
- `user-research`：訪談／問卷／逐字稿 lane

## 版本

- 5.1.1 → 6.0.0：新增 `/research` 第一層保守 router；自然語言推斷與低信心升級；合併 Agent-Reach、last30days、deep-research、user-research、qmd 與 ARIS 的適用方法；強度／assurance 兩軸；deep/large checkpoint/resume 與 artifact STALE；原 Vera 成為 native deep core。
- 4.1.0 → 5.0.0 重構：第二輪雙通道併行、新增第三輪反方稽核、禁詞 SSOT 獨立檔案、移除 7 個舊版子技能、移除 profile 設定檔（對標名單與品質規則內建於 SKILL.md）。
- 5.0.0 → 5.1.0：調研模式（competitor／vendor-dd／academic）、證據分級與深度門檻、必答問題庫、主管機關目錄 SSOT（併入 PR #1）、第一輪 agent-reach（reach.py）、覆蓋矩陣與預算停損（budget.py）、清除舊的身分設定用語。
- 5.1.0 → 5.1.1：併入 evidence-research-report 證據政策（依主張類型分級、主張處理、逐項語意核對、移除第三方模型核對）、深度編排 deep-mode.md（工作包→工作稿→綜合）、競品格式改八章（需求背景與目標、範圍與方法）、建議結論須有明確傾向、簡體中文機械檢查。
- 6.2.0 → 6.3.0：併入 evidence-research-report 剩餘資產——禁詞補頁名／倉庫路徑 token、`validate_report.py` 新增憑證與本機路徑外洩掃描、`evals/evals.json` 行為評測集、`scripts/search_web.py` 多引擎搜尋通道；三個原子目錄拷貝移除，本 repo 為唯一權威。
- 6.3.0 → 6.4.0：預算改雙層上限（借鏡 open_deep_research）——總量天花板依模式（competitor 120／80 等），>36 格才降額且搜尋不再降到 1；`competitor-single` 改為加深而非縮減；`fill` 機械化下限（≥2 個不同來源，`--sole` 例外）；保留池前提放寬為額度用盡也可加碼；牆鐘 90→120。提速：`reach.py read` 多 URL 平行、`check_urls` 跨網域平行、WP 子代理上限 3→5、camofox 健康探測只探一次。
