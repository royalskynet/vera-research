# Routing Rules

欄位與閾值以 `scripts/route.py` 為準；範例表由 `tests/test_routing_examples.py` 逐列驗證。

## 目錄

1. 任務分類
2. 能力選擇
3. 深度升級
4. 執行協定
5. 故障處理
6. Assurance 與續跑

## 1. 任務分類

先建 Task Profile，再選工具。

### Source scopes

- `web`：公開頁、官方網站、新聞、資料集、文件。
- `social`：指定貼文、帳號、社群或平台，不做廣泛趨勢。
- `recent-social`：近期意見、趨勢、評價、互動、跨社群討論。
- `local`：私有筆記、Markdown、本機知識庫。
- `human`：訪談、問卷、逐字稿、參與者研究。
- `code`：GitHub repo、issue、PR、release、程式碼搜尋。
- `academic`：論文、DOI 主張、文獻回顧。

只有任務真的跨證據類型時才使用多個 scope。

### Freshness

- `timeless`：歷史或穩定資料。
- `current`：當前狀態，必須上網複核。
- `window`：明確 7／30／90 天等期間。

### Rigor

- `lookup`：窄問題或指定物件取用。
- `verify`：核實主張並檢查矛盾。
- `deep`：產出可長期使用、決策級研究。

### Complexity

- `simple`：單一主體、單一主問題、單一證據類。
- `compound`：比較、多主體或兩種證據類。
- `large`：至少三個獨立軸、全面／系統性要求、正式研報、高證據量或遺漏會改變決策。

### Classification confidence

- `high`：URL、期間、交付、研究類型、驗證要求明確。
- `medium`：主題清楚但深度／邊界未明；quick 候選自動升 verified。
- `low`：極短、泛化「研究 X」或多種合理解讀；強度自動升一級。

### Privacy/action

- `public`：匿名公開來源。
- `authenticated`：登入、cookie、session 或私有 API。
- `private`：本機／私有材料。

招募、外聯、付費問卷、發布、登入、cookie 取用均屬外部動作，須明確授權。

## 2. 能力選擇

依序套用：

1. 尊重使用者明確指定能力，除非違反安全或任務範圍。
2. `local` 加 `qmd`。
3. `human` 加 `user-research`。
4. `recent-social` 加 `last30days`。
5. `web`、`code`、`academic`、直接 `social` 或官方核實，加 `agent-reach`。
6. 強度達 `verified`、`deep`、`large`，固定加原生 `deep-research`。
7. deep 沒有來源 lane 時補 `agent-reach`。
8. 不因能力已安裝便自動加入。
9. 使用者明確點名能力可加入，但不能繞過隱私／權限 gate。

## 3. 深度升級

### Quick

- 1–2 個聚焦查詢。
- 優先第一手來源。
- 窄問題獲答即停止。
- 僅限分類信心 high；否則至少 verified。

### Verified

- 3–5 個查詢角度。
- 重要主張至少兩個獨立來源群。
- 可得時至少一個第一手來源。
- 保留矛盾與精確日期。
- 只對重大缺口追加定向查詢。

### Deep

- 5–8 個角度、至少三類來源。
- 保存 source／evidence／claim／run ledger。
- outline refinement、最強反論、bounded delta queries。
- 高風險任務至少為 deep。

### Large

- 先定 scope 與成功條件。
- 拆 8–12 個獨立查詢角度。
- 至少四類相關來源。
- 每個重大主張至少三個獨立來源群。
- 保存 source／evidence／claim 狀態。
- 納入支持方、反方、失敗模式與缺失證據。
- 反方檢查後，對重大缺口做有界 delta queries。
- 覆蓋門檻通過即停；來源數本身不是完成條件。
- 未明確授權多代理時，用單 session 實作。

## 4. 執行協定

### 未選 deep

1. 本機取私有背景。
2. 取公開第一手證據。
3. 加近期社群脈動。
4. 在授權內加入人類證據。
5. 以 inline citations 與 limitations 綜合。

### 選中 deep

1. 先用本專案深度角色定 scope 與 plan。
2. 各來源 lane 僅負責獨立角色。
3. 正規化來源 identity，去除共同上游重複。
4. 把證據送回深度角色做 triangulation 與 critique。
5. 只做 gap-specific delta queries。
6. 產出要求的 artifact，披露降級 lane。

## 5. 故障處理

- 能力缺少：走 declared fallback 並標示降級。
- Doctor=`warn`：不得當 active；取得授權滿足條件或 fallback。
- 同一路徑失敗兩次：停止變體重試，改走一次替代路徑。
- 來源衝突：保留雙方，解釋來源強度與日期差。
- 無充分證據：回 `insufficient_evidence` 與最接近的可支持發現。
- 使用者改 scope：重新分類後才繼續。

## 6. Assurance 與續跑

- `informational`：一般答案；WARN 可交付但須披露。
- `decision`：競品／採購／策略比較；FAIL/BLOCKED/ERROR/STALE 阻擋完成。
- `audit`：vendor-dd／背調；上述加 MISSING，所有必要稽核都要 verdict artifact。
- deep/large 用 `run_state.py` checkpoint；resume 前驗 artifact hash。
- 同一缺口兩次無新證據後做一次 structural pivot，再無結果即關閉，不跑同義詞迴圈。
