# Capability Map

每個能力只承擔一種主要角色；只有證據類型不同時才組合。

| 能力 | 主要角色 | 選用時機 | 不可當作 |
|---|---|---|---|
| `agent-reach` | 公開資料與平台取用 | URL、官方網站、GitHub、指定社群、RSS、影音、即時公開事實 | 完整研究方法或自動真相裁判 |
| `last30days` | 近期社群脈動 | 最近評價、趨勢、互動、社群正在討論什麼 | 外部事實已發生的證明 |
| `deep-research` | 原生 Vera 範圍、覆蓋、三角驗證、反方、補查、綜合與交付驗證 | 所有 verified／deep／large；競品、盡調、高風險、正式報告 | 外部必要安裝；每次明確窄查詢的包裝 |
| `user-research` | 人類證據 | 訪談／問卷設計、逐字稿綜合、參與者研究 | 一般網搜；合成使用者亦不可代替真人母體 |
| `qmd` | 私有本機檢索 | Markdown、筆記、知識庫、歷史本地研究 | 程式碼搜尋或外部網搜 |

本專案原三輪流程就是 `deep-research` 實作，並吸收外部上游的方法概念。若另有專用 `deep-research` Skill，只有使用者明確指定或其領域契約更窄時才交由外部 Skill。

## 常見組合

- `agent-reach + last30days`：官方／即時事實＋社群脈動。
- `agent-reach + deep-research`：公開取用＋verified 以上統一驗證。
- `qmd + agent-reach`：私有背景＋即時外部事實，保持隱私邊界。
- `agent-reach + user-research`：desk research＋人類研究。
- `qmd + agent-reach + last30days + deep-research`：私有背景、公開事實、近期聲量的大型混合研究。

除非真的需要人類證據或使用者提供研究材料，否則不加 `user-research`。競品研究預設 assurance=`decision`；第三方廠商背調預設 assurance=`audit`。

## 可用性

lane 清單與探測以 `scripts/lanes.py` 為準（`lanes.py doctor --json`，輸出為快照非保證）。

以當前 host 的 Skill catalog 為準；單有 binary 不等於已安裝 agent-facing Skill。

Agent Reach channel：

- `status == "ok"`：可自動使用。
- `status == "warn"`：部分安裝／設定；取得授權並滿足條件後才可使用。
- `status == "off"` 或 `"error"`：不可用。
- `active_backend` 不可覆蓋非 `ok` 狀態。

不得因 router 選到能力便自動安裝、登入、匯入 cookie 或啟用瀏覽器權限。

## Fallback

- 缺 `agent-reach`：用 host 內建 web search/fetch；登入態平台不可用。
- 缺 `last30days`：用 Agent Reach 做有界近期搜尋，明示缺少互動權重與跨平台趨勢評分。
- 外部缺 `deep-research`：不降級；使用本專案原生 Vera 核心。
- 缺 `user-research`：只做研究設計或使用者提供材料的綜合，不宣稱已招募或訪談。
- 缺 `qmd`：用 `rg` 做本機 Markdown 關鍵字檢索。
