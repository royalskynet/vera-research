# 派工 deep 執行蒐集（沙箱外，純 CLI 通道）

第一輪、第二輪的蒐集迴圈可整包外包給 deep 執行人（`deep-run`，沙箱外）。主 session 只出計畫與驗收。

**為什麼值得外包**：`reach.py` 與 `camofox_fetch.py` 都在發網路請求**之前**先扣 `budget.py`，而 `WebSearch`／`WebFetch` 工具繞不進 `budget.py`。把蒐集交給只有 Bash 的 deep，預算閘門才是硬的——主 session 自己查是軟的。

**deep 的能力邊界不是工具集，是任務檔**：它缺的只有 Agent／WebFetch／WebSearch／MCP 四個 Claude 工具；agent-reach 整套是 CLI，不受影響。任務檔沒寫死的事它一律不做，所以計畫必須把指令逐字寫全，不留「照慣例」。

## 蒐集通道（2026-09-24 deep 端六項實測全通）

| 用途 | 指令 | 定位 |
|---|---|---|
| **搜尋／發現** | `reach.py search "<query>" --cell <格> --max N` | **唯一入口**（Exa 語意檢索經 `mcporter`；免鑰可跑，接上金鑰後放寬並發，接線步驟見 README §前置） |
| **讀取** | `reach.py read <URL> --cell <格>` | 預設（Jina Reader） |
| 多頁批次 | `reach.py read <URL>... 或 @urls.txt --save-dir <目錄> --cell <格>` | 一輪讀完、全文落檔，stdout 只印 PATH／CHARS；STATUS 帶 `:TRUNCATED` 表示 stdout 版被截，判「未見」前要 grep 落檔全文 |
| **讀取備援** | `camofox_fetch.py <URL> --cell <格>` | 只在下方「不足判準」命中時 |
| 反爬搜尋 | `camofox_fetch.py --search "<query>"` | 只在 Exa 三次查詢仍空手時 |
| 名冊／互動查詢頁 | `camofox_fetch.py <名冊 URL> --cell <格>` | 依 `registry-directories.md` 的第一輪通道標記，不等失敗才升級 |
| 名冊大檔（CSV >20 KB） | `budget.py spend fetch <格>` 後 `curl -sSL -o <檔> <URL>` 再 `grep -i <主體名>` | `reach.py read` 截 20 KB 會誤判「未見」；`registry-directories.md` 有標 `curl` 的來源用此列 |
| GitHub | `gh search repos\|code "<query>" --limit N` | `deep-run` 注入 `GH_TOKEN`；**必須單獨原子指令**，串接會被 wrapper hook 擋 |
| 社群平台 | 先 `agent-reach doctor --json` 看 `active_backend` 再選命令 | 只有題目需要多社群觀點時才開 |

## Exa MCP 的實際工具表（2026-10 實測，勿照抄過時文件）

`agent-reach` 的 `references/search.md` 宣稱 Exa「無需 API key」且列出 `get_code_context_exa`——**兩點都已不成立**。以 `mcporter list exa --schema` 為準：

| 工具 | 認證需求 | 本 repo 現況 |
|---|---|---|
| `web_search_exa(query, numResults?, objective)` | 免鑰即可 | `reach.py search` 唯一入口 |
| `web_fetch_exa(urls, maxCharacters?)`（預設 3000 字）| 免鑰即可 | **未使用**，讀頁走 Jina Reader |
| `web_search_advanced_exa` | 免鑰即可，但須 `?tools=` opt-in | 未使用，擴充提案見 `docs/exa-surface-expansion-proposal.md` |
| `agent_run(query?, runId?, systemPrompt?, outputSchema?, input?)` | **須 OAuth 或金鑰**才出現在工具表 | 未使用，同上 |

認證三態：免鑰 `https://mcp.exa.ai/mcp`／OAuth `?login`／金鑰加 `x-api-key` header。金鑰怎麼接見 README §前置。

`get_code_context_exa` 在現行工具表**已不存在**，照抄會直接失敗。進階用法與擴充提案見 `docs/exa-surface-expansion-proposal.md`。

## ledger 定位（預算失控的第一破口）

計畫內每條腳本指令前都帶 `RESEARCH_BUDGET=<ledger 絕對路徑>`。不設就回退吃 cwd 的 `./.research-budget.json`——cwd 一偏，不是扣錯帳就是完全不記帳。

## 退 camofox 的判準（寫進計畫，deep 不得自行發揮）

`reach.py read` 回 **exit 5**（STATUS 欄 `BLOCKED:<reason>`）才升級 camofox，**每個 URL 最多升級一次**（`camofox_fetch.py` 的 `escalation_gate` 會記 `cells[<cell>]["escalated"]`）。

**exit 5 不是唯一入口**：HTTP 200 但正文只有導覽列（例如國家清單在 JS 延遲載入區塊）不會觸發 exit 5，卻一樣是缺口。agent-reach 各輪結束後仍 OPEN／空著落的格，一律進 **camofox 深入輪**：`budget.py phase deep --gaps <格,...>`，額度另計，逐頁落檔，`budget.py verify` 逐字核實後才 `fill`（規格見 SKILL.md「預算預設」B 節）。

**沒有常駐 camofox REST 服務的機器**：設 `CAMOUFOX_PYTHON=<裝有 camoufox 套件的 python>`，`camofox_fetch.py` 在 `localhost:9377` 不通時改用它逐頁子行程渲染（en-US 語系、networkidle＋5 秒）；兩者都沒有才回 exit 3 SKIP。

升級一次仍不足 → `budget.py nonew <格>`，標 `[⚠️ 頁面不可達]` 不引用，換下一個 URL。**不得同一 URL 反覆兩條通道互試。**

## 迴圈與 exit code

開跑前逐格 `budget.py ask <格> "<題>"...` 登記必答題（依使用者指令生成；沒登記的格 spend 回 `EXHAUSTED reason=no_questions`）。迴圈：`budget.py spend` → `reach.py`（不足才 `camofox_fetch.py`）→ 有料 `budget.py fill <格> <N>`（每個來源一次）＋逐題 `budget.py answer <格> <Q#> <N>`／`--none "<理由>"`（第 2 個不同來源且登記題全結案才 FILLED）／無料 `budget.py nonew <格>` → `budget.py status`。

| code | 意義 | 動作 |
|---|---|---|
| 0 | 成功 | 照常 `fill`／`nonew` |
| 2 | 抓不到／搜尋 0 筆 | 標 `[⚠️ 頁面不可達]` 不引用，**不重試** |
| 3 | 工具不可用（camofox 服務沒跑、**瀏覽器啟不起來**／`mcporter` 失聯） | **停手回報**，不得自行 `launchctl` 載入，改走另一通道或結束該輪。camofox `/health` 回 ok 不等於瀏覽器可用（懶啟動）；stderr 出現 `camofox browser cannot launch` 是工具故障不是頁面問題，同批其餘 URL 已印 `SKIP`，**不換 URL 重試**，主 session 依 fixindex 9694 修安裝位置 |
| 4 | 預算閘門 | 立刻 `budget.py close <格>` |
| 5 | 擋頁／短內文／封鎖狀態碼 | 升級 camofox，同 URL 只升一次 |

**`--max N` 不保證回 N 筆**（實測 `--max 3` 回 2 筆屬正常）。回得少**不是失敗**，不得換關鍵字重刷——那是預算外流的主要破口。

## 分批派工（vendor-dd 實測：一次一批、序列跑）

同一 ledger 不能兩個 deep 同時扣，所以按維度切成序列任務，每批一份任務檔（`feedback_workorder_new_file_per_dispatch`）：

1. **批 A＝D1–D3**：D1 撬出法定名、登記號、前身、關聯法人 → 主 session 驗收後 `budget.py entities …` 寫入主體解析表（D2／D6 的 spend 前置依賴）。
2. **批 B＝D4／D5／D7／D8**：能力、AML、資安、事故，只需法定名。
3. **批 C＝D6／D9 最後**：任務檔注入 `entities` 的法定名、前身、LEI **與高管姓名**（`--people`），聲譽與實控人搜尋才打得到 PEP／訴訟／舊案；沒名字派 C 等於白跑。

每批任務檔要求台帳固定格式 `| R<n> | 等級 | 標題 | URL | 查閱日期 | 頁面日期 | 摘錄 | 支持題號 |`，初稿以 `[D1R2]` 標籤引用，定稿 `scripts/number_cites.py draft.md --sources work/round1/D*.md work/round2/sources.md` 一次編號；標籤缺來源會回 exit 1 列 `MISSING`。

主 session 驗收每批看三件事：格是否 `FILLED`、台帳每列是否有頁面日期與摘錄、`budget.py status` 的餘額是否與任務檔預期一致（少扣＝有 WebFetch 繞過閘門，多扣＝重試）。

## 沙箱假陰性

`reach.py read`／`curl r.jina.ai` 在主 session 沙箱回 `URLError`，在 deep 端（沙箱外）正常 200。**不得拿主 session 的連線失敗推論 deep 也不通**，反之亦然；通道可用性一律以 deep 端實測為準。

## 停止條件（deep 不會自己收手，只有機械計數器會）

- `budget.py spend` 回 `EXHAUSTED`／`HALT` ＝ 立刻 `budget.py close <格>`，不得換關鍵字重試。
- `budget.py status` 印 `NEXT: draft` ＝ 蒐集結束，立刻停抓、開始寫初稿。「再查一下」「補最後一個來源」一律禁止。
- 同格連續 2 次無新事實 → `nonew` 自動 `CLOSED`。
- **預算用盡＝這一輪蒐集停手**，不等於資訊足夠。deep 端一律照停：剩餘空格先寫中性事實，不得自行加碼、不得換關鍵字重刷。
- **加碼只有主 session 能開**。定稿前主 session 覆核，某格若有明確證據缺口且已鎖定一手來源 URL，由主 session 跑 `budget.py topup <格> --fetch N --search N [--minutes M] --reason "<缺口＋來源>"` 重開該格再派一輪；理由寫進 ledger 的 `topups`。deep 的任務檔**禁止**出現 `budget.py topup`。「沒預算」不是不查證的理由，「查過且無一手來源」才是。加碼前提：格 `CLOSED` 且 close reason 以 `channel:` 開頭、同格未曾 topup、`--reason` 含 `http`、加碼量不超 15% 尾段保留池餘額。
