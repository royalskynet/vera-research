# vera-research — `/research` router + deep-research 引擎

**简体中文**：[README.md](README.md)｜**繁體中文**：[README.zh-TW.md](README.zh-TW.md)｜**English**：[README.en.md](README.en.md)

`vera-research` 是名为 `research` 的 [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) skill。v6.0.0 把 `/research` 升级为第一层保守判断器：依任务性质路由 `agent-reach`、`last30days`、`qmd`、`user-research`，并用原 Vera 三轮流程作原生 deep core。只有明确窄查找走 quick；模糊任务至少 verified，低信心升一级；竞品预设 decision assurance，第三方厂商背调／尽调预设 audit assurance。

原本加密交易所风控研究保留为 domain profile：`competitor`、`vendor-dd`、`academic`。命中时仍用覆盖矩阵、预算停损、双通道补洞、反方审核与**简体中文**正式报告；一般研究不套用交易所名单或风控格式。

目前声明版本：`6.8.0`（见 `SKILL.md` 的 `metadata.version`）。

## 快速安装

```bash
git clone https://github.com/royalskynet/vera-research ~/.claude/skills/research
```

安装到此为止。这个 repo 本身就是 skill：clone 到 `~/.claude/skills/research` 就把 `SKILL.md` 放进 Claude Code 预期的位置，重新开一个 session 后 `/research` 即可用。内附脚本只用 Python 标准函数库加 Bash，直接从 clone 运行——不用 build、不用安装套件。

已经有本机副本的话，symlink 一样可以：

```bash
ln -s "$PWD/vera-research" ~/.claude/skills/research
```

安装后可这样试跑：

```bash
python3 ~/.claude/skills/research/scripts/route.py --pretty "今年 RAG 评测基准有哪些变化"
```

## Router V2

```bash
scripts/route.py "全面调研三家 KYC 供应商的能力、牌照与负面纪录，产出背调报告" --pretty
```

输出包含 Task Profile、`quick|verified|deep|large`、`informational|decision|audit`、能力组合、运行阶段、品质闸门、缺能力 fallback、隐私／权限 gate 与 checkpoint 契约。完整规格见 `docs/research-router-v2-spec.md`，路由范例见 `references/routing-examples.md`。

Deep／large 可续跑并检查产物是否过期：

```bash
scripts/route.py "<request>" --pretty > route.json
scripts/run_state.py init --route route.json --run-dir ./research-run
scripts/run_state.py checkpoint --run-dir ./research-run --phase scope-plan-coverage --verdict PASS --artifact ./scope.md
scripts/run_state.py status --run-dir ./research-run
```

## Effort 档位

`scripts/budget.py init --effort full|medium|low` 控制流程长度与交付物。证据规则三档相同：牌照一律对 S1 监管名册、每条主张挂 `[N]`、先抓原文再写、禁词与简体中文检查。未指定时用 `medium`。

| 档位 | 交付物 | 目标时长 |
|---|---|---|
| `full` | 九章完整版（原三轮流程全跑） | 60–80 分钟 |
| `medium`（预设） | 重点版，含信任评分 | 35–40 分钟 |
| `low` | 速览版，不评分 | 10–15 分钟 |

- `medium`：免逐题 `ask`／`answer` 记帐；缺口补查只一轮（≤4 格），不开深入轮；直接写重点版；第三轮反方审核照跑，放背景运行。
- `low`：只查主体、牌照、负面纪录、制裁名单与产品范围；无缺口补查、无反方审核；15 分钟墙钟到即用已有事实成稿，格式见 `references/report-format-vendor-dd-quick.md`。
- 三档共用：页面正文只落档，事实实时追加到 `work/facts.md`，避免 context 压缩后重抽；同一名册最多试 2 次；制裁名单 CSV 比对并入第一轮。

时长依据一次 vendor-dd 实测：`full` 跑 68 分钟，其中 context 压缩后重建事实约 7 分钟、逐题记帐回合约 11 分钟。`medium`／`low` 的时长为推估，尚未实测。

## 原生 Vera 三轮内核

1. **第一轮** 选模式 → `scripts/budget.py init --mode …` 建「平台×维度」覆盖矩阵 → 依 `questions-<mode>.md` 的必答问题与三视角补充题生成查找 → WebSearch，回空或不足即走 agent-reach（`scripts/reach.py search` 走 Exa，失败时另有一轮性的 ddgs 备援；WebFetch 失败走 `reach.py read` 走 Jina）→ 每格达 `evidence-standards.md` 门槛才 `FILLED` → `budget.py status` 印 `NEXT: draft` 即停止搜集写初稿。每次搜索／抓取都先记帐；预算用尽＝这一轮停手，定额加码规则见 `references/deep-dispatch.md`。
2. **第二轮** 只处理缺口（上限依模式），每格「两通道各恰一次」：通道 A 本地反侦测渲染（`scripts/camofox_fetch.py`，含 `--search`）；通道 B agent-reach 换角度／换语言／替代来源（reach.py 或子代理）。牌照类缺口优先下沉 `registry-directories.md` 的名册。
3. **集成** 补强写回原段落并充实相邻内容，跨维度交叉一次；定稿不留任何工作阶段标记；`scripts/check_report.sh <报告> --mode <m>` 检查来源总数、字数与简体中文；铁律 4 逐项语意核对（不抽样、不送第三方模型）。
4. **第三轮** 独立子代理反方审核（含 `self-reported-only`／`register-unchecked` 旗标），主 session 七道闸门裁决后改写定稿。

报告产出物禁词 SSOT 见 `references/forbidden-words.md`。

## 目录

| 档 | 职责 |
|---|---|
| `SKILL.md` | 角色定位与产出品质、调研模式、深度标准摘要、预算与停损、铁律 1–4、三轮 SOP |
| `docs/research-router-v2-spec.md` | Router V2 完整契约、强度、assurance、pipeline、schema 与验收 |
| `docs/exa-surface-expansion-proposal.md` | 扩大 Exa 搜索面的提案 |
| `references/upstream-review.md` | 六个上游＋原 Vera 的 commit、授权、安全审查与采舍 |
| `references/capabilities.md` | 五种能力的单一责任、组合、可用性与 fallback |
| `references/routing-rules.md` | Task Profile、高估优先、四强度、assurance 与续跑规则 |
| `references/router-evidence-policy.md` | 所有路由输出须遵守的来源分级与独立性规则 |
| `references/routing-examples.md` | 请求 → 路由的范例表 |
| `references/evidence-standards.md` | 来源分级 S1–S5（各级能／不能证明什么）、主张处理规则、逐项语意核对、深度门槛、名册对照写法 |
| `references/questions-competitor.md` | competitor 六维度必答问题与每平台一手来源 |
| `references/questions-vendor-dd.md` | vendor-dd D1–D9 必答问题、三视角提问、跨维度交叉 |
| `references/registry-directories.md` | 主管机关目录、制裁清单、公司登记、处分、法院、卡组织名录的 URL SSOT 与 fallback 链 |
| `references/report-format.md` | competitor／academic 八章格式（需求背景与目标、范围与方法、对比、深度分析、差距、建议结论、来源） |
| `references/deep-mode.md` | 深度编排：起点资产盘点、工作包（WP）拆分、工作稿、综合主报告、定稿门槛清单 |
| `references/deep-dispatch.md` | 把第一、二轮搜集整包交给沙箱外运行人的派工说明 |
| `references/report-format-vendor-dd.md` | vendor-dd 八章格式（含调研范围与方法、逐维度宣称／核实／评述／风险等级） |
| `references/report-format-vendor-dd-brief.md` | vendor-dd 重点版（评分总览、主体／合规／可靠性／能力四表、调用者前提逐条核实、子维度依据），`medium` 档位直接产出；`full` 档位可由完整版重排 |
| `references/report-format-vendor-dd-quick.md` | vendor-dd 速览版（`low` 档位）：主体与牌照、负面与制裁、产品范围、覆盖范围 |
| `references/vendor-trust-score-rubric.md` | vendor-dd 信任分数（可选）：六子维度权重（20/20/20/10/20/10）、三桶（合规 40／能力 30／可靠性 30）、A+–D 五级、各子项评分区间、跨行业调整 |
| `references/round2-merge.md` | 第二轮两通道分派表、缺口上限、融合与充实规则、checklist |
| `references/round3-devils-advocate.md` | 反方子代理 prompt 模板、旗标、证据包 schema、七道闸门、裁决规则 |
| `references/forbidden-words.md` | 禁词 SSOT（fenced ```text``` 供脚本截取）＋例外 |
| `scripts/budget.py` | 覆盖矩阵＋预算 ledger（`--mode` 预设、spend／refund／trail／nonew／fill／close／gaps／phase／status、`--selftest`） |
| `scripts/route.py` | 自然语言／明确 profile 的 deterministic Router V2 |
| `scripts/run_state.py` | Deep／large checkpoint、resume manifest、verdict 与 artifact hash／STALE 验证 |
| `scripts/lanes.py` | 能力登录表与可用性探测（`doctor --json`） |
| `scripts/reach.py` | agent-reach 胶水：`search`（Exa via mcporter，失败时单次 ddgs 备援）、`read`（Jina Reader）；带 `--cell` 自动记帐 |
| `scripts/camofox_fetch.py` | 走常驻 camofox-browser REST `:9377` 的渲染与反爬搜索；带 `--cell` 依 ledger 拒绝超额 |
| `scripts/search_web.py` | 多引擎搜索通道，带顺序 fallback 链 |
| `scripts/validate_report.py` | 引用结构、`--check-list` 逐项主张→来源清单、`--check-urls` 存活、`--lang zh-hans` 繁体误用检查 |
| `scripts/check_report.sh` | validate_report.py ＋ 禁词 grep ＋ `--lang` 语言检查胶水；`--selftest` |
| `scripts/devils_advocate.sh` | 第三轮引擎选择：第二模型优先（codex → opencode），都不可用才退回主 session 派 subagent |
| `scripts/number_cites.py` | 初稿 `[D1R2]` 标签 → 依首次出现重编 `[N]`＋产来源表；同 URL 合并、缺来源回 exit 1 |
| `scripts/exa_usage_watch.py` | Exa 估算用量达免费额度 80% 时警示一次 |
| `evals/evals.json` | 行为评测集 |
| `tests/` | pytest 测试套件，涵盖路由、预算 ledger、reach、camofox、引用编号与外泄扫描 |
| `.githooks/pre-push` | 推前自检 |

## 前置

`scripts/reach.py` 依赖 `mcporter` CLI 调用 Exa（第一轮外部搜索 fallback）。若 `which mcporter` 为空：

```bash
npm i -g mcporter
```

reach.py 会先查 `$PATH`，再回退扫 `~/.nvm/versions/node/*/bin/`、`~/.local/bin/`、`~/.npm-global/bin/`；找不到才输出 `[reach] mcporter not found; install: npm i -g mcporter` 并回非零 exit code。nvm 切版时装到当前 node 版本即可，不需 admin。

内附脚本 Python 3.9 以上即可运行，CI 跑 3.12。`pytest` 只有跑测试套件时才需要。

### 选用：接上 Exa 密钥（放宽并发）

Exa 免钥 MCP 有额度上限，实测 5 路并发就有 2 路撞 `HTTP 429`。有密钥时 `reach.py` 放宽到 5 路并发。要生效需要**两件事同时成立**：

1. 密钥可读：`EXA_API_KEY` 环境变量，或 `~/.config/vera-research/EXA_API_KEY.txt`（`_exa_env()` 会读，密钥不落 stdout）。
2. mcporter 真的会送 header——`~/.mcporter/mcporter.json` 的 `mcpServers.exa.headers` 要有 `x-api-key`：

```bash
mcporter config add exa --url https://mcp.exa.ai/mcp \
  --header 'x-api-key=${EXA_API_KEY}' --scope home
```

值写 `${EXA_API_KEY}` 占位（mcporter 运行时展开），设置档不存密钥。**只做第 1 步不会生效**：`reach.py` 读得到密钥却没 header 可送，等于仍是匿名额度。此时 `reach.py` 会在 stderr 出声一次并维持单路，不会静默用 5 路把额度打爆。

## 设置

不使用本机设置档。对标名单预设为 SKILL.md「角色定位与产出品质」所列主流交易所，用户指定时以指定为准；报告一律不署名、不含任何组织身分信息；渲染与搜索通道固定走 `scripts/` 内置脚本。ledger 档 `.research-budget.json` 与 `reports/` 不入库。

## 输出语言

调研报告正文用**简体中文**（公司名、产品名、技术术语保留原文；用户明确指定其他语言时以指定为准，并以 `check_report.sh … --lang any` 跳过语言检查）。`SKILL.md` 与 `references/`（运行方文档，不是给读者的）用繁体中文。

## 关联 skill

- `agent-reach`：第一轮的 Exa／Jina／社区通道，第二轮通道 B
- `last30days`：近期社区期间、聚类与交互信号 lane
- `qmd`：本机 Markdown 检索 lane
- `user-research`：访谈／问卷／逐字稿 lane

## 开发

```bash
git config core.hooksPath .githooks
python -m pytest tests/ -q
bash scripts/check_report.sh --selftest
python scripts/budget.py --selftest
```

pre-push hook 会扫描追踪档的禁词字面并跑禁词自检；GitHub Actions 的 `check` workflow 每次 push 与 pull request 跑同一组。分支命名与 commit 格式见 `CONTRIBUTING.md`，未解事项见 `issue.md`。

## 版本

- 6.7.0 → 6.8.0：添加 effort 档位 `full`／`medium`／`low`（`budget.py init --effort`），`medium` 为预设并直出重点版；添加速览版格式；`devils_advocate.sh` 修 `set -u` 下变量名后接全角标点的 unbound 错误；平行抓取测试改用 Barrier 判定，不再依赖墙钟。
- 5.1.1 → 6.0.0：添加 `/research` 第一层保守 router；自然语言推断与低信心升级；合并 Agent-Reach、last30days、deep-research、user-research、qmd 与 ARIS 的适用方法；强度／assurance 两轴；deep/large checkpoint/resume 与 artifact STALE；原 Vera 成为 native deep core。
- 4.1.0 → 5.0.0 重构：第二轮双通道并行、添加第三轮反方审核、禁词 SSOT 独立文件、移除 7 个旧版子技能、移除 profile 设置档（对标名单与品质规则内置于 SKILL.md）。
- 5.0.0 → 5.1.0：调研模式（competitor／vendor-dd／academic）、证据分级与深度门槛、必答问题库、主管机关目录 SSOT（并入 PR #1）、第一轮 agent-reach（reach.py）、覆盖矩阵与预算停损（budget.py）、清除旧的身分设置用语。
- 5.1.0 → 5.1.1：并入 evidence-research-report 证据政策（依主张类型分级、主张处理、逐项语意核对、移除第三方模型核对）、深度编排 deep-mode.md（工作包→工作稿→综合）、竞品格式改八章（需求背景与目标、范围与方法）、建议结论须有明确倾向、简体中文机械检查。
- 6.2.0 → 6.3.0：并入 evidence-research-report 剩余资产——禁词补页名／仓库路径 token、`validate_report.py` 添加凭证与本机路径外泄扫描、`evals/evals.json` 行为评测集、`scripts/search_web.py` 多引擎搜索通道；三个原子目录拷贝移除，本 repo 为唯一权威。
- 6.3.0 → 6.4.0：预算改双层上限（借镜 open_deep_research）——总量天花板依模式（competitor 120／80 等），>36 格才降额且搜索不再降到 1；`competitor-single` 改为加深而非缩减；`fill` 机械化下限（≥2 个不同来源，`--sole` 例外）；保留池前提放宽为额度用尽也可加码；墙钟 90→120。提速：`reach.py read` 多 URL 平行、`check_urls` 跨网域平行、WP 子代理上限 3→5、camofox 健康探测只探一次。