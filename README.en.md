# vera-research — `/research` router + deep-research engine

**简体中文**：[README.md](README.md)｜**繁體中文**：[README.zh-TW.md](README.zh-TW.md)｜**English**：[README.en.md](README.en.md)

`vera-research` is a [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) skill named `research`. Release 6.0.0 promoted `/research` into a first-layer conservative classifier: it routes by task shape to `agent-reach`, `last30days`, `qmd` and `user-research`, and uses the original Vera three-round process as its native deep core. Only clearly narrow questions may take the quick path; ambiguous tasks get at least verified, and low confidence escalates one level. Competitor studies default to decision assurance; third-party vendor due diligence defaults to audit assurance.

The original crypto-exchange risk research is preserved as domain profiles: `competitor`, `vendor-dd` and `academic`. When one of them matches, the skill still applies the coverage matrix, budget stop-loss, dual-channel gap filling, devil's advocate audit and Simplified Chinese formal report format. General research does **not** inherit the exchange list or the risk-control format.

Current declared version: `6.8.0` (see `metadata.version` in `SKILL.md`).

## Quick install

```bash
git clone https://github.com/royalskynet/vera-research ~/.claude/skills/research
```

That is the whole install. The repository *is* the skill: cloning it into `~/.claude/skills/research` puts a `SKILL.md` where Claude Code expects it, and `/research` becomes available in a new session. The bundled scripts are standard-library Python plus Bash and run straight from the clone — no build step, no package to install.

Already have a checkout? Symlinking works just as well:

```bash
ln -s "$PWD/vera-research" ~/.claude/skills/research
```

Verify the copy after installing:

```bash
python3 ~/.claude/skills/research/scripts/route.py --pretty "what changed in RAG evaluation benchmarks this year"
```

## Router V2

```bash
scripts/route.py "全面調研三家 KYC 供應商的能力、牌照與負面紀錄，產出背調報告" --pretty
```

The output carries the Task Profile, the intensity (`quick|verified|deep|large`), the assurance level (`informational|decision|audit`), the chosen capability combination, execution phases, quality gates, missing-capability fallbacks, privacy/permission gates and the checkpoint contract. The full contract lives in `docs/research-router-v2-spec.md`; worked examples live in `references/routing-examples.md`.

Deep and large runs are resumable, and stale artifacts are detected:

```bash
scripts/route.py "<request>" --pretty > route.json
scripts/run_state.py init --route route.json --run-dir ./research-run
scripts/run_state.py checkpoint --run-dir ./research-run --phase scope-plan-coverage --verdict PASS --artifact ./scope.md
scripts/run_state.py status --run-dir ./research-run
```

## Effort levels

`scripts/budget.py init --effort full|medium|low` sets how long the process runs and what it delivers. The evidence rules are the same at every level: licences are always checked against the S1 regulator register, every claim carries `[N]`, the source page is fetched before anything is written, and the forbidden-word and Simplified Chinese checks run. The default is `medium`.

| Level | Deliverable | Target time |
|---|---|---|
| `full` | Nine-chapter full report (the whole three-round process) | 60–80 min |
| `medium` (default) | Condensed report with trust score | 35–40 min |
| `low` | Quick scan, no score | 10–15 min |

- `medium`: no per-question `ask`/`answer` bookkeeping; one gap-filling round (≤4 cells) and no deep round; writes the condensed report directly; the round-3 devil's advocate audit still runs, in the background.
- `low`: covers only the entity, licences, adverse records, sanctions lists and product scope; no gap filling and no devil's advocate audit; when the 15-minute wall clock runs out it writes up the facts it has. Format: `references/report-format-vendor-dd-quick.md`.
- All levels: page bodies go to files only and each fact is appended to `work/facts.md` as it is found, so nothing has to be re-extracted after a context compaction; each register gets at most 2 attempts; sanctions-list CSV screening runs in round 1.

The times come from one measured vendor-dd run: `full` took 68 minutes, of which about 7 went to rebuilding facts after context compactions and about 11 to per-question bookkeeping turns. The `medium` and `low` times are estimates and have not been measured yet.

## The native Vera three-round core

1. **Round 1 — collect.** Pick the mode, then `scripts/budget.py init --mode …` to build a platform × dimension coverage matrix. Generate queries from the mandatory questions in `questions-<mode>.md` plus supplementary questions from three viewpoints, then WebSearch. If search comes back empty or thin, fall back to agent-reach: `scripts/reach.py search` runs Exa, and `scripts/reach.py read` runs Jina Reader when WebFetch fails. A cell only becomes `FILLED` once it clears the threshold in `evidence-standards.md`. Stop collecting when `budget.py status` prints `NEXT: draft`. Every search and fetch is booked first; running out of budget ends the round. The top-up rules are in `references/deep-dispatch.md`.
2. **Round 2 — close gaps only** (capped per mode). Each gap gets exactly one attempt per channel: channel A is the local anti-detection renderer (`scripts/camofox_fetch.py`, which also has `--search`); channel B is agent-reach from a different angle, language or source (reach.py or a subagent). Licence-type gaps go straight to the registry list in `registry-directories.md`.
3. **Integrate.** Reinforce the original paragraphs, enrich neighbouring content, cross-check once across dimensions. The final draft carries no work-phase markers. `scripts/check_report.sh <report> --mode <m>` checks source count, length and Simplified Chinese; iron rule 4 then verifies every claim individually (no sampling, and no third-party model).
4. **Round 3 — devil's advocate.** An independent subagent audits the conclusion, flags `self-reported-only` and `register-unchecked`, and the main session adjudicates through seven gates before the final rewrite.

The forbidden-word SSOT for report output is `references/forbidden-words.md`.

## Repository layout

| File | Responsibility |
|---|---|
| `SKILL.md` | Role definition and output quality, research modes, depth standards summary, budget and stop-loss, iron rules 1–4, three-round SOP |
| `docs/research-router-v2-spec.md` | Full Router V2 contract, intensities, assurance, pipeline, schema and acceptance |
| `docs/exa-surface-expansion-proposal.md` | Proposal for widening the Exa search surface |
| `references/upstream-review.md` | Commits, licences, security review and adopt/drop decisions for six upstreams plus the original Vera |
| `references/capabilities.md` | The single job of each of the five capabilities, their combinations, availability and fallbacks |
| `references/routing-rules.md` | Task Profile, over-estimation-first policy, four intensities, assurance and resume rules |
| `references/router-evidence-policy.md` | Source tiers and independence rules that all router output must obey |
| `references/routing-examples.md` | Worked request → route table |
| `references/evidence-standards.md` | Source tiers S1–S5 (what each tier can and cannot prove), claim handling, per-claim semantic verification, depth thresholds, registry wording |
| `references/questions-competitor.md` | Six mandatory competitor dimensions and their first-party sources |
| `references/questions-vendor-dd.md` | vendor-dd mandatory questions D1–D9, three-viewpoint prompting, cross-dimension checks |
| `references/registry-directories.md` | URL SSOT and fallback chains for regulators, sanctions lists, company registries, enforcement actions, courts and card schemes |
| `references/report-format.md` | competitor/academic eight-chapter format (background and goals, scope and method, comparison, deep analysis, gaps, recommendations, sources) |
| `references/deep-mode.md` | Deep orchestration: starting-asset inventory, work package (WP) split, working drafts, synthesis, finalization checklist |
| `references/deep-dispatch.md` | Handing round 1–2 collection to an out-of-sandbox executor |
| `references/report-format-vendor-dd.md` | vendor-dd eight-chapter format (with scope and method, plus per-dimension claim/verification/commentary/risk level) |
| `references/report-format-vendor-dd-brief.md` | vendor-dd condensed version (score overview, four tables, caller premises verified one by one, sub-dimension basis); produced directly at `medium`; at `full` it can be re-arranged from the full version |
| `references/report-format-vendor-dd-quick.md` | vendor-dd quick scan (`low` level): entity and licences, adverse records and sanctions, product scope, coverage |
| `references/vendor-trust-score-rubric.md` | Optional vendor-dd trust score: six sub-dimension weights (20/20/20/10/20/10), three buckets (compliance 40 / capability 30 / reliability 30), grades A+–D, score bands, cross-industry adjustment |
| `references/round2-merge.md` | Round 2 two-channel dispatch table, gap caps, merge and enrichment rules, checklist |
| `references/round3-devils-advocate.md` | Devil's advocate subagent prompt template, flags, evidence-pack schema, seven gates, adjudication rules |
| `references/forbidden-words.md` | Forbidden-word SSOT (fenced ```text``` block the scripts read) plus exceptions |
| `scripts/budget.py` | Coverage matrix + budget ledger (`--mode` default, spend/refund/trail/fill/close/gaps/phase/status, `--selftest`) |
| `scripts/route.py` | Deterministic Router V2 for natural language and explicit profiles |
| `scripts/run_state.py` | Deep/large checkpoints, resume manifest, verdicts, artifact hash/STALE verification |
| `scripts/lanes.py` | Capability registry and availability probes (`doctor --json`) |
| `scripts/reach.py` | agent-reach glue: `search` (Exa via mcporter, with a one-shot ddgs fallback), `read` (Jina Reader); `--cell` books the ledger automatically |
| `scripts/camofox_fetch.py` | Rendering and anti-bot search through the resident camofox-browser REST service on port 9377; `--cell` refuses over-budget calls |
| `scripts/search_web.py` | Multi-engine search channel with an ordered fallback chain |
| `scripts/validate_report.py` | Citation structure, `--check-list` per-claim → source checklist, `--check-urls` liveness, `--lang zh-hans` Traditional-Chinese misuse check |
| `scripts/check_report.sh` | Glue for validate_report.py + forbidden-word grep + `--lang` check; `--selftest` |
| `scripts/devils_advocate.sh` | Round 3 engine selection: second model first (codex → opencode), subagent only when neither is available |
| `scripts/number_cites.py` | Renumbers draft `[D1R2]` tags to sequential `[N]` by first appearance and emits the source table; merges identical URLs, exits 1 if a source is missing |
| `scripts/exa_usage_watch.py` | Warns once when estimated Exa spend reaches 80% of the free monthly quota |
| `evals/evals.json` | Behavioural evaluation set |
| `tests/` | pytest suite covering routing, budget ledger, reach, camofox, citations and leak scanning |
| `.githooks/pre-push` | Pre-push self-check |

## Prerequisites

`scripts/reach.py` shells out to the `mcporter` CLI to reach Exa (the first-round external search fallback). If `which mcporter` comes back empty:

```bash
npm i -g mcporter
```

reach.py first checks `$PATH`, then falls back to scanning `~/.nvm/versions/node/*/bin/`, `~/.local/bin/` and `~/.npm-global/bin/`. If it still finds nothing it prints `[reach] mcporter not found; install: npm i -g mcporter` and exits non-zero. Installing into the current node version is enough under nvm; no admin rights needed.

Python 3.9 or newer covers every bundled script; CI runs 3.12. `pytest` is needed only to run the test suite.

### Optional: an Exa key to lift the concurrency limit

The keyless Exa MCP tier has a quota cap — in practice two of five concurrent requests already hit `HTTP 429`. With a key, `reach.py` widens to 5 concurrent searches. Two things must both hold:

1. The key is readable: the `EXA_API_KEY` environment variable, or `~/.config/vera-research/EXA_API_KEY.txt` (`_exa_env()` reads it; the key never goes to stdout).
2. mcporter actually sends the header — `mcpServers.exa.headers` in `~/.mcporter/mcporter.json` must carry `x-api-key`:

```bash
mcporter config add exa --url https://mcp.exa.ai/mcp \
  --header 'x-api-key=${EXA_API_KEY}' --scope home
```

Write the literal `${EXA_API_KEY}` placeholder (mcporter expands it at run time), so the config file never stores the secret. **Step 1 alone does not work**: reach.py can read the key but has no header to send, which is still the anonymous quota. In that case reach.py says so once on stderr and stays serial.

## Configuration

There is no local config file. The default benchmark list is the set of mainstream exchanges named in SKILL.md under "role definition and output quality"; when you name your own targets, yours win. Reports are unsigned and carry no organizational identity information. The rendering and search channels are fixed to the built-in scripts under `scripts/`. The ledger file `.research-budget.json` and `reports/` are not committed.

## Output language

Research reports are written in Simplified Chinese (company names, product names and technical terms keep their original spelling; use `--lang any` when the user explicitly asks for another language). `SKILL.md` and the `references/` files — the instructions meant for the agent, not the reader — are in Traditional Chinese.

## Related skills

- `agent-reach` — the Exa/Jina/social channel in round 1, and channel B in round 2
- `last30days` — recent social sentiment, clustering and interaction signals
- `qmd` — local Markdown retrieval lane
- `user-research` — interviews, questionnaires and transcript lane

## Development

```bash
git config core.hooksPath .githooks
python -m pytest tests/ -q
bash scripts/check_report.sh --selftest
python scripts/budget.py --selftest
```

The pre-push hook scans tracked files for forbidden literals and runs the forbidden-word selftest; the `check` GitHub Actions workflow runs the same set on every push and pull request. See `CONTRIBUTING.md` for branch naming and commit format, and `issue.md` for open items.

## Version history

- 6.7.0 → 6.8.0: new effort levels `full`/`medium`/`low` (`budget.py init --effort`), with `medium` as the default and delivering the condensed report directly; new quick-scan format; `devils_advocate.sh` fixed for the `set -u` unbound error when a full-width punctuation mark follows a variable name; the parallel-fetch test now uses a Barrier instead of a wall-clock threshold.
- 5.1.1 → 6.0.0: added the first-layer conservative `/research` router; natural-language inference with low-confidence escalation; folded in the applicable methods of Agent-Reach, last30days, deep-research, user-research, qmd and ARIS; separate intensity and assurance axes; deep/large checkpoint/resume with artifact STALE detection; the original Vera became the native deep core.
- 4.1.0 → 5.0.0 refactor: parallel dual-channel round 2, new round 3 devil's advocate audit, forbidden-word SSOT split into its own file, removal of 7 legacy sub-skills, removal of the profile config file (the benchmark list and quality rules now live in SKILL.md).
- 5.0.0 → 5.1.0: research modes (competitor / vendor-dd / academic), evidence tiers and depth thresholds, mandatory question library, regulator directory SSOT (folded in from PR #1), first-round agent-reach (reach.py), coverage matrix and budget stop-loss (budget.py), and removal of the old identity wording.
- 5.1.0 → 5.1.1: folded in the evidence-research-report evidence policy (tiering by claim type, claim handling, per-claim semantic verification, no third-party-model verification), deep-mode orchestration (work package → working draft → synthesis), competitor format expanded to eight chapters (background and goals, scope and method), recommendations required to state a clear lean, and a mechanical Simplified Chinese check.
- 6.2.0 → 6.3.0: folded in the remaining evidence-research-report assets — forbidden words extended to repo path tokens, credential and local-path leak scanning in `validate_report.py`, the `evals/evals.json` behaviour set, and `scripts/search_web.py` as a multi-engine search channel; the three atomic directory copies were removed and this repository is the single authority.
- 6.3.0 → 6.4.0: budget switched to a two-tier cap (mirroring open_deep_research) — the overall ceiling depends on the mode (competitor 120 / 80 etc.), the quota only drops for grids larger than 36 cells and search no longer drops to 1; `competitor-single` now deepens instead of shrinking; `fill` got a mechanical floor (≥2 distinct sources, with `--sole` as the exception); the reserve pool precondition was relaxed so a top-up is allowed even after the quota is exhausted; wall clock 90 → 120. Speedups: parallel multi-URL `reach.py read`, cross-domain parallel `check_urls`, WP subagent cap 3 → 5, and a single camofox health probe.