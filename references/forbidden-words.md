# 禁詞 SSOT（報告產出物）

本檔是 `scripts/check_report.sh` 的禁詞單一權威來源。清單放在下方 fenced ```text``` 區塊，每行一個 `grep -E` 正則；腳本只擷取該區塊，不在腳本內重抄（跨檔重抄視同漂移）。

## 掃描對象

- **報告產出物**（最終交付的 .md）：掃完整清單，**章節標題（`##` `###` 行）與正文同判**，命中任一行即判未定稿。研究流程語（方法学／本次调研／核心发现／调研目标／调研范围／本报告）最常在章節標題殘留，特別注意。
- **本 repo 的格式文件**（`report-format*.md`、`report-patterns.md`）：`check_report.sh --selftest` 掃其 `##`／`###` 章名，命中即 FAIL。規範互斥要在自檢時爆，不是讓每份產出各自手改章名。
- **倉庫自身**（SKILL.md、其他 references、scripts、README）：只掃「內部」「skills-manager」兩個字面（`.githooks/pre-push`），本檔因必須列出禁詞而排除在自掃之外。SOP 描述本就需要使用「第一輪／反方／裁決」等詞，不套完整清單。

## 例外（命中但允許保留）

- 參考資料表的「查閱日期」欄位（引用格式組成部分）。
- 被引來源標題原文（來源本身即含該術語，例如某 API 文件）。
- 章名「執行摘要」「調研摘要」。
- 「本次已查阅的公开来源未能确认……」「资料截至 YYYY-MM」是允許的中性表述。`[推论]` **不再是例外**：查不到來源的主張直接刪除，不標記保留。
- 英文 token 一律加 `\b` 字界，避免誤中 `background`、`prefetch` 等自然詞；`403`／`429` 亦加字界，避免誤中一般數字。
- 差距分析表的 ✅／⚠️ 符號（結論符號，非工作階段標記）。

## 中性替代措辭

| 過程性 | 學術性 |
|---|---|
| 「經抓取後仍無材料」 | 「公開載體上無相應材料」 |
| 「重試檢索的結果」 | 「補充可核實事實」 |
| 「返回不再受支持」 | 「目前不再公開」 |
| 「vendor 自報」 | 「供應商自報」 |
| 「marketing 頁面」 | 「其網站首頁」 |
| 「待內部確認」「待跟內部確認」「待確認」「待核實」「暫無查到」 | 刪除該主張，或改寫為可核實的中性事實（如「公开帮助页未列出」） |
| 「內部盤點」「內部文檔」 | 「公司規劃」「公開文件」 |
| 「內部彙報」 | 「組織彙報」 |
| 調用者口述的內部事實（會議名稱、內部統計、前次決策經過） | 刪除；改寫為以公開來源可核實的調研目標陳述（規則見 SKILL.md 鐵律 6） |

```text
\bfetch\b
Firecrawl
r\.jina\.ai
web\.archive\.org
archive\.today
\bCamoufox\b
\bcamofox\b
\bcurl\b
\bWayback\b
\bsnapshot\b
渲染
爬取
\bpipeline\b
\bSPA\b
\b(429|403)\b
\bagent\b
\bsubagent\b
\bdelegate\b
\bExplore\b
general-purpose
cross-model
跨模型
agent.?reach
重試
重试
二次檢索
\bretry\b
補齊
补齐
韌性
韧性
\brollback\b
修正後
經抓取後
第一輪
第二輪
第三輪
第一轮
第二轮
第三轮
\bround ?[123]\b
two-round
\bround\b
本轮
本輪
上一轮
上一輪
下一轮
下一輪
補強
补强
定向補強
缺口清單
缺口清单
資料缺口清單
资料缺口清单
反方
\bdevil
\baudit\b
稽核
裁決
裁决
證據包
证据包
\bpacket\b
adjudicat
內部
内部
\binternal\b
\bvendor\b
\bmarketing\b
\bfallback\b
\bworkaround\b
待核實
待核实
待確認
待确认
待要求
待補來源
待补来源
資料缺口
资料缺口
頁面不可達
页面不可达
資料來源存疑
资料来源存疑
資料不足
资料不足
暫無查到
暂无查到
尚無法確認
尚无法确认
無法核實
无法核实
❓
覆蓋矩陣
覆盖矩阵
\bledger\b
EXHAUSTED
budget\.py
reach\.py
camofox_fetch\.py
\bmcporter\b
\bExa\b
\bJina\b
留给.{0,8}(领导|管理层|决策者|业务).{0,4}定夺
留給.{0,8}(領導|管理層|決策者|業務).{0,4}定奪
可视情况决定
可視情況決定
建议进一步评估
建議進一步評估
方法学
方法學
本次调研
本次調研
调研目标
調研目標
调研范围
調研範圍
调研对象
調研對象
调研维度
調研維度
核心发现
核心發現
本报告
本報告
\[推论\]
\[推論\]
\bllm-wiki\b
\braw/
內部倉庫
内部仓库
^#{1,6}\s*(摘要|概念|實體|实体|分析)-
\bwiki\b
```
