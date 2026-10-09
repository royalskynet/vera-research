# 第三輪反方稽核協定（Devil's Advocate）

第三輪**必跑，不可省略**：凡交付正式報告（vendor-dd、competitor、academic 皆同），整合定稿後一律做一次反方稽核；稽核未完成＝`BLOCKED`，不得交付。

**引擎順序（第二模型優先）**：跑 `${CLAUDE_SKILL_DIR}/scripts/devils_advocate.sh <報告絕對路徑> <證據包絕對路徑>`。

- 腳本依序試 `codex`（`--search` 開即時網搜）→ `opencode`；產出證據包且過格式檢查即 exit 0，印 `ENGINE=<名>`。
- 腳本 exit 3（印 `FALLBACK=subagent reason=…`：兩個第二模型都不可用、證據包格式不合，或報告含私人 PII 不能送外部模型）→ 主 session 派遣一次獨立 `Agent(general-purpose, run_in_background:false)`，prompt 用下方模板。

不論哪個引擎，反方只拿到報告、本協定、輸出路徑三樣東西。第二模型與 subagent 都沒有對話歷史，這就是獨立上下文；主 session 不得附任何自己的結論、摘要或「我覺得哪裡弱」。

規範改寫自 evidence-debate-audit（packet-schema／adjudication-rules／debate-protocol）。與原版的差異：反方**可以自行上網**找反證，但每條反證必須實際開啟來源頁、附 URL、附摘錄；主 session 對正反雙方套同一組證據閘門。

## 派遣 prompt 模板（腳本與 subagent 共用，原樣填入，不增刪）

```
你是本報告的反方稽核者。你只有三個輸入，其他一概沒有：
1. 報告：<報告絕對路徑>
2. 協定：<${CLAUDE_SKILL_DIR}/references/round3-devils-advocate.md 的絕對路徑>
3. 輸出：<證據包絕對路徑，例如 <報告目錄>/audit/devils-advocate.md>

先完整讀協定，再完整讀報告。依協定「範圍：挑爭點」挑 2–5 個爭點，對每個爭點上網搜尋並實際開啟來源頁找最強反證，
按「反方輸出 schema」把證據包寫到輸出路徑。每條反證缺 URL 或缺摘錄即無效；找不到實據就寫 NO_EVIDENCE_BACKED_OBJECTION，不得湊數。
不要改報告，不要引用你未實際開啟的頁面，不要推測派工者的立場。完成後回覆證據包路徑與爭點數。
```

## 鐵律

**Force opposing positions, never opposing facts.** 強制對立立場，不強制相反事實。反證查無實據就回 `NO_EVIDENCE_BACKED_OBJECTION`，不得為湊數捏造、拼貼或斷章取義。每條反證都必須實際開啟來源頁，記下 URL 與摘錄；摘錄須忠於原文立場。

## 範圍：挑爭點

1. 讀出報告的核心結論（通常在摘要與「建議與啟示」）與支撐它的關鍵主張。
2. 找最可能**削弱或窄化**核心結論的 2–5 個爭點，每個爭點標一個旗標：
   - **inference**：結論由證據跨步推導，無直接來源
   - **extrapolation**：來源只覆蓋範圍 A，報告套到範圍 B
   - **no-source**：當事實寫、零引用
   - **single-source**：只有一個來源、無佐證
   - **stale**：來源早於已知的監管／市場／產品變動
   - **self-reported-only**：整段只有 S4（新聞稿／合作方／自報）來源，卻寫成既成事實
   - **register-unchecked**：牌照／認證／會員資格類宣稱沒有對應監管機關名冊的對照結果
   - **unanswered**：報告「本次要回答的問題」中某題，或標題下的一句話結論，沒有被正面回答——答非所問、只列事實不接成答案、以「未能核實」迴避其實有來源可答的題、或一句話結論與主要結論方向不一致。`validate_report.py --answer-map` 只證明答案句存在，不證明它真的回答了問題；這個旗標審的是後者
   - **verdict-leak**：S1 名冊對照結果是「查無／主體不符」（硬負面），但對應維度的風險等級或摘要結論卻標「中/低」或以「需以正式文件複核」稀釋，未據實升等（見 evidence-standards.md「風險結論映射」）
3. 依影響力排序（若成立能否改變或窄化核心結論），只留 1–5 條。
4. 每個爭點至少一次搜尋與一次實際開頁；同一爭點最多開 3 個來源，不得無限擴搜。

## 反方輸出 schema（子代理 Write 到輸出路徑）

```markdown
# Devil's Advocate Evidence Pack

Report: <報告絕對路徑>
Reviewed: <YYYY-MM-DD>
Core conclusion as read: <一句話，用報告原文措辭>

## 爭點 1
FLAG: inference | extrapolation | no-source | single-source | stale | self-reported-only | register-unchecked | unanswered | verdict-leak
TARGET: <報告原句或表格儲存格，逐字引用>
ATTACK: premise | inference | scope | comparison | omission | recommendation | evasion
OBJECTION: <最強反方論點；查無實據則寫 NO_EVIDENCE_BACKED_OBJECTION>
EVIDENCE:
- URL: <已實際開啟的完整 URL>
  DATE: <頁面日期或「未標示」>
  EXCERPT: <原文摘錄，≤ 80 字>
IMPACT: retain | narrow | reverse
```

- 每條 EVIDENCE 三欄缺一不成立；沒有 EVIDENCE 的爭點 OBJECTION 必須是 `NO_EVIDENCE_BACKED_OBJECTION`。
- 例外：`FLAG: unanswered` 的證據就是報告本身，EVIDENCE 改寫為 `- REPORT: <報告中問題原句，逐字>` 與 `- REPORT: <報告中對應答案原句，逐字；找不到寫 ABSENT>` 兩行，ATTACK 填 `evasion`。若主張「其實有來源可答」，仍須另附一條 URL／DATE／EXCERPT 實開證據。
- TARGET 必須逐字對得上報告，方便主 session 定位改寫。

## 七道證據閘門（主 session 對雙方同套）

| Gate | 問題 |
|---|---|
| Existence | 來源可讀、辨識正確？ |
| Directness | 來源直接支持該主張？ |
| Subject | 是同一實體或同一受規範類別？ |
| Time | 日期支持報告的資料截止點？ |
| Scope | 管轄、產品、族群、限定語是否被保留？ |
| Entailment | 結論是否超出證據所能確立？ |
| Counter-evidence | 該方是否處理了相關的反面證據？ |

補充（配合 verdict-leak 旗標）：稽核時需檢查**負面核實結果是否被結論誠實反映**——S1 名冊「查無／主體不符」不得在風險矩陣或摘要被「中/低」或「需複核」稀釋；僅 S4 自報或「未檢索到」的維度不得標「低」。

不以來源數量計分：一條直接的官方原文可勝過多條間接轉述。

## 裁決規則

- `PRO_WINS`：核心結論仍被支持，反方論點未過閘門或無實質影響 → 報告不變。
- `CON_WINS`：反方證據過閘門且推翻該主張 → 依 round2-merge.md 的融合規則改寫原段落，並把反方來源編入參考清單掛 `[N]`。
- `SPLIT`：雙方各確立實質部分 → 保留支持內容，在原句加上條件或限制，反方來源同樣掛 `[N]`。
- `unanswered` 爭點 `CON_WINS` → 在原位補上直接答案（能／不能／有條件／未能核實＋理由），同步更新 `audit/answer-map.md` 該列的報告原句，再重跑 `check_report.sh --answer-map`。
- `UNRESOLVED`：現有記錄無法裁定 → 原位補一句中性措辭（如「公開來源對此口徑不一」），不猜測、不另立章節、不得寫「待確認」「待核實」「待要求」等表述。

裁決結果與證據包留在工作目錄（`audit/`），不進報告文本；報告只反映改寫後的內容。

## 停損條件

所有爭點裁決完成即停止；不開第二輪辯論，不因反方「講得自信」而直接讓步，主 session 必須逐爭點寫下裁決理由（留在 `audit/verdicts.md`）。到達來源數或爭點數上限時記錄限縮，不擴大稽核。牆鐘到時以已完成的爭點裁決，未開始的爭點記錄限縮。
