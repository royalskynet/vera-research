# 主管機關公開目錄（牌照／監管資質核對）

本檔是 SKILL.md「盡職調查類主題：牌照／監管資質下沉主管機關目錄」鐵律的來源清單。凡報告主張「XX 保有某轄區牌照」，一律先查下列官方目錄交叉核對，查無則據實標「公開目錄未列」。

借鏡 OpenSanctions 的 `datasets/` 結構：每來源標注官方 URL、查詢方式、資料格式、更新頻率、查不到時的 fallback。本檔是執行方文件，不進報告。

**本清單非封閉、不限縮**：所列機構是「已核對／已踩坑」的落地清單，不是窮舉。遇新轄區／新主體／新主管機關，照同一列格式（主管機關｜目錄 URL｜查詢方式｜資料格式｜第一輪通道）擴列；不在本表者不代表無名冊可查，以「官方目錄優先」判準現場決定通道，不因表內沒有就略過下沉。

## 一、主管機關目錄（牌照核對）

「第一輪通道」標記執行者該用哪條通道，不用自行判斷：`reach.py read`＝有公開 CSV／API 直接抓；`camofox_fetch.py`＝互動查詢頁／擋抓取，第一輪就渲染（不等第二輪）。

| 轄區 | 主管機關 | 目錄／查詢入口 | 查詢方式 | 資料格式 | 第一輪通道 |
|------|---------|--------------|---------|---------|-----------|
| 美國 | FinCEN | MSB 註冊商查詢 `https://www.fincen.gov/msb-registrant-search`（各州選擇器 `https://www.fincen.gov/msb-state-selector`） | 網頁 | CSV（OpenSanctions 每週抓 `us_fincen_msb`）| `reach.py read`（FinCEN 頁或 OpenSanctions `us_fincen_msb` CSV）|
| 加拿大 | FINTRAC | MSB 註冊處公開搜尋 `https://fintrac-canafe.canada.ca/msb-esm/` | 網頁動態搜尋 | 無公開 CSV（需網頁查）| `camofox_fetch.py`（動態搜尋頁）|
| 香港 | 公司註冊處 | 信託及公司服務持牌人登記冊 `https://www.tcsp.cr.gov.hk` | 公開搜尋 + 開放資料 CSV `https://www.tcsp.cr.gov.hk/open-data/licensees.csv` | CSV | `reach.py read`（CSV 直接抓）|
| 立陶宛 | 立陶宛央行（Lietuvos bankas） | 金融市場參與者名冊（含 EMI），入口 `https://www.lb.lt/en/`（站點擋一般抓取） | 網頁互動查詢 | 無獨立 API | `camofox_fetch.py`（第一輪渲染）|
| 新加坡 | MAS | 金融機構總目錄（FID）`https://eservices.mas.gov.sg/fid` | 網頁 + JSON API `https://eservices.mas.gov.sg/api/action/datastore/search.json` | datastore API | `reach.py read`（datastore API）|
| 英國 | FCA | 金融服務登記冊 `https://register.fca.org.uk` | 網頁搜尋 | 無公開 CSV | `camofox_fetch.py`（互動搜尋）|
| 香港 | SFC | 持牌人及註冊機構公眾紀錄冊 `https://www.sfc.hk/en/Regulatory-functions/Intermediaries/Licensing/Register-of-licensed-persons-and-registered-institutions` | 網頁搜尋 | 無公開 CSV | `camofox_fetch.py`（互動搜尋）|
| 新加坡 | MAS | 投資者警示名單 `https://www.mas.gov.sg/regulation/fintech/investor-alert-list` | 網頁 | 無 | `reach.py read` |
| 歐盟（MiCA） | ESMA | 過渡期 CASP 名冊 `https://www.esma.europa.eu/sites/default/files/2024-12/CASPS.csv`（欄位說明 `.../Description_of_the_fields_in_the_interim_MiCA_register.csv`） | 整檔下載後 `grep -i <主體名>` | CSV（400+ 列，>20 KB） | **`curl -sSL -o CASPS.csv <URL>`**——`reach.py read` 截 20 KB，目標列在後段就誤判「未見」 |
| 法國（MiCA 通報） | AMF | 白名單總頁 `https://www.amf-france.org/en/warnings/white-lists`（每主體一頁 `.../white-lists/casp/<slug>`，含授權日期、LEI、服務類別） | 網頁 | HTML | `reach.py read` |
| 列支敦士登 | FMA | MiCAR 名冊 `https://www.fma-li.li/en/financial-intermediaries/financial-institutions-division/activities-under-micar/register`；全體持牌人 `https://www.fma-li.li/en/financial-centre/register-of-licensees`；處分 `https://www.fma-li.li/en/supervision-regulation/enforcement` | 互動查詢 | 無公開 CSV | `camofox_fetch.py`（第一輪渲染）；處分頁 `reach.py read` |

## 二、制裁 / PEP / 負面清單

| 來源 | URL | 說明 |
|------|-----|------|
| OFAC SDN | `https://sanctionssearch.ofac.treas.gov/` | 美國制裁名單 |
| OpenSanctions | `https://github.com/opensanctions/opensanctions` | 各國制裁/PEP/公司結構化資料集（每源一個 YAML + crawler）|
| UN Consolidated List | `https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list` | 聯合國制裁 |
| EU Sanctions Map | `https://sanctionsmap.eu` | 歐盟制裁 |
| 英國 HMT | `https://www.gov.uk/.../financial-sanctions` | 英國制裁 |

## 三、公司註冊 / 股權 / 實控人

| 來源 | URL | 說明 |
|------|-----|------|
| 新加坡 ACRA | `https://www.acra.gov.sg`（BizFile+ 需登入，摘要 API `data.gov.sg` 部分公開） | 公司註冊、董事、實繳資本 |
| 英國 Companies House | `https://find-and-update.company-information.service.gov.uk` / API `https://developer-specs.company-information.service.gov.uk` | 免費公開 |
| OpenCorporates | `https://opencorporates.com` | 多國公司註冊聚合 |
| ICIJ Offshore Leaks | `https://offshoreleaks.icij.org` | 離岸公司／信託查詢 |
| 列支敦士登 Handelsregister | Firmenindex `https://handelsregister.li`（官方 Öffentlichkeitsregister `https://www.oera.li` 擋一般抓取） | 登記號（`FL-XXXX.XXX.XXX-X`）、董事、前身名稱；互動頁走 `camofox_fetch.py` |
| GLEIF LEI | `https://search.gleif.org/#/search/simpleSearch=<LEI 或名稱>`；API `https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]=<名稱>` | 免費；核對法定名、註冊地址、登記號與名冊所載 LEI 是否同一主體（S1，便宜，第一輪就跑） |

## 四、監管處分 / 執法公告

| 來源 | URL | 說明 |
|------|-----|------|
| FinCEN 執法 | `https://www.fincen.gov/news-room/enforcement-actions` | 美國裁罰 |
| MAS 執法 | `https://www.mas.gov.sg/regulation/enforcement/enforcement-actions` | 新加坡裁罰 |
| HKMA 執法 | `https://www.hkma.gov.hk/eng/key-functions/banking/` | 香港 |
| 金融業負面新聞 | agent-reach 多語言關鍵字搜尋 + Exa | 替代來源 |

## 五、法院、判決與投訴（D6 用）

| 來源 | URL | 說明 |
|------|-----|------|
| 美國法院 docket（CourtListener / RECAP） | `https://www.courtlistener.com/` | 案卷、起訴狀、Order、和解／同意令原文；反爬，第一輪用 `reach.py read` 或 `camofox_fetch.py` 渲染，不等第二輪 |
| 美國法院案卷（Justia Dockets） | `https://dockets.justia.com/` | 起訴狀 PDF、案卷程序事件；查民事沒收、集體訴訟、和解結案 |
| 集體訴訟起訴狀存檔 | ClassAction.org 等第三方存檔 | 起訴狀 PDF 原文（指控非法院認定，須標「原告指控」） |
| 香港司法機構判決 | `https://www.judiciary.hk/en/judgments_legal_reference/judgments.html` | 公開 |
| 新加坡 eLitigation | `https://www.elitigation.sg/` | 公開判決 |
| Trustpilot／ScamAdviser | `https://www.trustpilot.com/`／`https://www.scamadviser.com/` | S5，只能寫「有用戶反映」；Trustpilot 反爬走第二輪 |
| Reddit／Twitter | agent-reach 社群通道（`opencli reddit search`／`twitter search`） | S5 |

**執法／訴訟查詢鐵律**（D6 必做，不可只搜品牌名）：

1. **先取法定實體名**：從主體 S2 條款／官方文件（Terms、授權頁、牌照頁）撬出簽約主體與持牌主體的法律名稱（Limited／LLC／UAB 等），再拿這些名稱查 docket——品牌名查不到不算「無負面」。
2. **多方檢索**：每一實體用「法定名 + 品牌名 + 前身品牌 + 別名 + 創辦人／負責人姓名」各查一次訴訟與沒收。
3. **區分程序階段**：起訴狀指控 ≠ 法院認定；沒收／和解／撤訴（with prejudice）各是不同事實，照 evidence-standards「爭議、訴訟、制裁」寫。民事沒收（forfeiture）、同意令（consent order）、和解金額若有 docket 支持，屬 S1 硬證據。
4. **docket 是 S1**：CourtListener、Justia、PACER 案卷原文與官方執法公告同為 S1 等級；起訴狀 PDF 屬「原告指控」需標明。

## 六、卡組織與資安認證（D4／D7 用）

| 來源 | URL | 說明 |
|------|-----|------|
| Visa 全球服務商名錄（PCI DSS） | `https://www.visa.com/splisting/` | 公開查詢 |
| Mastercard SDP 合規服務商 | Mastercard 官網「Site Data Protection」合規名單 | 公開 |
| SOC 2／ISO 27001 | 出具機構之公開證書登錄（依報告所稱機構查） | 依機構 |

## 查不到時的 fallback 鏈

某目錄查不到該主體時，依序：

1. 確認查詢主體名稱正確（換註冊名／`UAB` ／`Limited` ／當地實體名）。
2. 換註冊轄區實體（同一集團在不同轄區有不同法律實體）。
3. agent-reach 換角度（公司本地名、股東關聯、歷史名稱）。
4. 仍查無 → 據實標「公開目錄未列」，不得升格為「已持牌」。

## 重點提醒

- **官方目錄 > 公司自報 > 新聞稿 > 供應商／競爭對手頁面**：優先序固定，越低順位來源只能作佐證，不得作為「已持牌」的唯一憑證。
- 每個「已核對」結論都要附目錄查詢 URL + 日期，供法務／風控覆核。
- **名冊「查無」前先確認拿到的是整檔，不是截斷片段**：`reach.py read` 對大 CSV 只回前 20 KB；列數 >100 的名冊一律 `curl -o` 整檔再 grep。
- **彙整站（thebanks.eu、CoinDesk 名錄等）的「授權日期」欄位定義不一**：對列支敦士登主體常是 TVTG 登記日，不是 MiCA CASP 授權日。多個日期並列寫進報告，各附一手名冊來源，不取其一。
