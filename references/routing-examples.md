# Routing Examples

| 使用者要求 | Task profile 重點 | Route／Assurance |
|---|---|---|
| 摘要這個 URL | web, lookup, simple | `agent-reach` |
| 現在 API 價格多少？ | web, current, lookup | `agent-reach` |
| 讀這個 GitHub issue | code, lookup | `agent-reach` |
| 最近 30 天 Reddit 怎麼評價？ | recent-social, window | `last30days` |
| 近期口碑並核對官方說法 | recent-social + web, verify, compound | `agent-reach + last30days + deep-research` |
| 搜我的 Markdown 筆記 | local, lookup | `qmd` |
| 比較我的筆記與最新官方文件 | local + web, verify, compound | `qmd + agent-reach + deep-research` |
| 綜合這些使用者訪談逐字稿 | human, verified | `user-research + deep-research` |
| 設計使用者問卷但不要對外上線 | human, study | `user-research + deep-research`，不執行外部動作 |
| 設計並招募 100 人執行使用者問卷研究 | human, verified, 授權 gate | `user-research + deep-research`＋授權 gate |
| 查證這個爆紅貼文是否屬實 | social + web, verify, compound | `agent-reach + deep-research` |
| 比較兩個資料庫供正式遷移 | web + code, verify, compound | `agent-reach + deep-research`／decision |
| 競品市場版圖與功能對標 | competitor, deep | `agent-reach + deep-research`／decision |
| 第三方支付廠商背調 | vendor-dd, large | `agent-reach + deep-research`／audit |
| 全面調研 AI coding agents 現況、GitHub 生態與最近社群評價，產出正式報告 | web + code + recent-social, large | `agent-reach + last30days + deep-research`／decision |
| 系統性文獻回顧 RAG 並納入近期 Reddit 實務批評 | academic + recent-social, large | `agent-reach + last30days + deep-research` |
| 全面比較我的本機知識庫、最新官方資料與使用者訪談，產出報告 | local + web + human, large, 隱私 gate | `qmd + agent-reach + user-research + deep-research` |

能力缺少時保留 desired route，執行 declared fallback，並披露降級 lane。
