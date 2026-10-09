# Upstream Capability Review

審查日期：2026-09-19。所有上游內容均視為不可信資料；只擷取可驗證的方法概念。沒有授權檔的專案不複製文字或程式碼。

| 上游 | 審查 commit | 授權 | 擇優吸收 | 不合併／限制 |
|---|---|---|---|---|
| [Agent-Reach](https://github.com/Panniantong/Agent-Reach) | `a19a171fa980a0785849596492e0af4db800c82f` | MIT | 平台／後端路由、read-only doctor、公開頁與指定平台取用、失敗 fallback | 不自動登入、讀 cookie、安裝 channel；不把 retrieval 當完整研究方法 |
| [last30days](https://github.com/mvanhorn/last30days-skill) | `beb7ed1868f034f198842174bfe2694e44b78363` | MIT | 期間解析、實體／handle resolution、跨平台訊號、互動權重、cluster-first 去重、近期來源與 web backfill | 不複製 2,000+ 行輸出契約；不執行 pipe-to-shell 安裝；社群不作事實真值；remote API／發布須另行授權 |
| [claude-deep-research-skill](https://github.com/199-biotechnologies/claude-deep-research-skill) | `f2f2c0fa4e7617ca84c86b63f4bb40f77a746933` | 未見 LICENSE | SCOPE→PLAN→RETRIEVE→TRIANGULATE→OUTLINE REFINE→SYNTHESIZE→CRITIQUE→PACKAGE；source/evidence/claim/run manifest；delta queries | 只吸收抽象方法；不複製程式／模板；不硬綁 search-cli、固定 Documents 輸出、自動開檔或多代理 |
| [user-research-skill](https://github.com/cookiy-ai/user-research-skill) | `21eea10a34d3c9b4e711e3d19f0457603dd33e19` | MIT | plan／synthesize／execute 三路由、qual/quant 分流、逐字稿分階段綜合、真人與 synthetic 分離 | 不自動導流、招募、付費、對外執行；Cookiy 只在使用者明確選擇且授權時使用 |
| [qmd-skill](https://github.com/levineam/qmd-skill) | `a2daa499d21d672465af5852caebe68e94d917bc` | 未見 LICENSE | 本機優先、BM25 first、semantic fallback、hybrid last、collection scope、冷啟動成本披露 | 只吸收抽象路由；不複製文件；不自動安裝 Bun/qmd、不自動下載模型、不把本機 corpus 送 hosted service |
| [Auto-claude-code-research-in-sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) | `341f914024d270dc5c8fa51337d1ad38829273aa` | MIT | effort／assurance 兩軸、checkpoint/resume、stall→structural pivot、source contribution receipt、候選先驗證、稽核 verdict、artifact hash／STALE、持久知識防自我污染 | 只取適合競品／廠商背調的控制面；不合併論文、GPU、實驗、自動改稿、LLM 分數收斂、83 skills、跨模型強制依賴或全域被動監控 |
| 原 `vera-research` | 本 repo `8f6f202` 基線＋工作樹既有 domain 增強 | 本專案 | 覆蓋矩陣、預算停損、S1–S5、entity resolution、雙通道補洞、反方稽核、逐主張與報告驗證 | 交易所名單、風控維度、簡體報告格式只限 domain profile，不污染一般研究 |

## 合成決策

### 採用

1. Router first：先判任務，再取資料。
2. Conservative escalation：分類不確定只升不降。
3. Source lanes：五種能力保持單一責任，不互相冒充。
4. Native deep core：Vera 作編排與品質核心，外部能力作 evidence provider。
5. Four ledgers：source、evidence、claim、run manifest。
6. Evidence-driven outline：證據可改綱要，不能靠想像擴題。
7. Cluster independence：按共同上游分群，而非 URL 計數。
8. Human/privacy gates：外部動作與私有資料分開授權。
9. Effort × assurance：搜尋廣度與交付稽核嚴格度分離；競品預設 decision，廠商背調預設 audit。
10. Resumable runs：deep/large 保存 phase checkpoint、來源貢獻與 artifact hash；續跑前檢查 STALE。
11. Structural pivot：兩次無新證據後只允許一次來源類型／法定實體／法域級 pivot，不做同義詞空轉。

### 拒絕

- 自動安裝、`curl | bash`、`sudo`、登入、cookie 擷取。
- 未經授權的招募、付費、發布與 hosted corpus 傳輸。
- 強迫所有任務使用多代理；host policy 與使用者授權優先。
- 固定輸出到使用者 Documents、自動開 HTML/PDF。
- 把來源中的提示詞、操作指令或「必須遵循」當成系統規則。
- 無 LICENSE 上游的程式碼、模板與長篇文字複製。
- 以 LLM 自評分數當完成條件；完成由 coverage、claim support 與 machine-readable verdict 決定。
- 全域被動記錄使用者 prompt／工具事件；持久化僅限使用者指定的 run/project 目錄。

## 安全結論

- `Agent-Reach`、`last30days`、`user-research` 有 MIT 授權；仍不直接 vendoring，以降低供應鏈與維護面。
- `deep-research`、`qmd-skill` 未見 LICENSE，僅進行 clean-room 方法重述與獨立實作。
- `last30days` 文件含 pipe-to-shell、credential、browser、remote API、發布路徑；全部保留在授權 gate 外，不進 router 自動執行面。
- Router 本身只做 deterministic planning，不讀 secret、不連網、不改外部狀態。
- ARIS repo 雖為 MIT，但依賴面與操作面遠超本技能需求；只獨立實作 assurance/checkpoint 小核心，不安裝其 MCP、hooks 或技能集。
