#!/usr/bin/env bash
# 第三輪反方稽核引擎選擇：第二模型優先（codex → opencode），都不可用才退回主 session 派 subagent。
# 用法：devils_advocate.sh <報告.md 絕對路徑> <證據包輸出絕對路徑>
# exit 0＝證據包已產出且過格式檢查（stdout 印 ENGINE=<名>）；3＝需主 session 派 subagent（stdout 印 FALLBACK=subagent reason=…）；2＝用法錯誤。
# 派給任何引擎的 prompt 一律取自 round3-devils-advocate.md「派遣 prompt 模板」（SSOT），只帶報告、協定、輸出三個路徑，不帶主 session 結論。
# env：DA_ENGINES（預設 "codex opencode"）、DA_TIMEOUT 秒（預設 1200）、DA_OPENCODE_MODEL（不設＝opencode 預設模型）。
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROTO="$(cd "$SCRIPT_DIR/../references" && pwd)/round3-devils-advocate.md"

[ $# -eq 2 ] || { echo "usage: $0 <report.md> <out.md>" >&2; exit 2; }
REPORT="$1"; OUT="$2"
[ -f "$REPORT" ] || { echo "report not found: $REPORT" >&2; exit 2; }
case "$REPORT$OUT" in /*/*) ;; *) echo "paths must be absolute" >&2; exit 2;; esac
mkdir -p "$(dirname "$OUT")"
WORKDIR="$(dirname "$OUT")"
TIMEOUT="${DA_TIMEOUT:-1200}"
TO_BIN="$(command -v gtimeout || command -v timeout || true)"

fallback() { echo "FALLBACK=subagent reason=$1"; exit 3; }

# 隱私閘（鐵則 6）：報告含私人 PII 就不送外部模型。公開登記的法人／高管姓名不擋——反方要用真名查證，匿名化會讓查證失效。
PII_RE='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|0x[0-9a-fA-F]{40}|\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b|\bT[1-9A-HJ-NP-Za-km-z]{33}\b|\b[0-9]{4}[ -]?[0-9]{4}[ -]?[0-9]{4}[ -]?[0-9]{4}\b|\+[0-9][0-9 ()-]{8,}[0-9]'
if grep -qE "$PII_RE" "$REPORT"; then
  fallback pii_in_report
fi

PROMPT="$(awk '/^## 派遣 prompt 模板/{f=1;next} f&&/^```$/{if(in_b){exit}else{in_b=1;next}} f&&in_b' "$PROTO" \
  | sed -e "s#<報告絕對路徑>#$REPORT#" \
        -e "s#<\${CLAUDE_SKILL_DIR}/references/round3-devils-advocate.md 的絕對路徑>#$PROTO#" \
        -e "s#<證據包絕對路徑，例如 <報告目錄>/audit/devils-advocate.md>#$OUT#")"
[ -n "$PROMPT" ] || fallback template_missing

pack_ok() {
  [ -s "$OUT" ] && grep -q "^# Devil's Advocate Evidence Pack" "$OUT" && grep -q '^## 爭點' "$OUT" \
    && grep -qE 'URL: https?://|NO_EVIDENCE_BACKED_OBJECTION' "$OUT"
}

run_engine() {
  local eng="$1"
  command -v "$eng" >/dev/null 2>&1 || return 1
  rm -f "$OUT"
  case "$eng" in
    codex)
      DA_OUT="$OUT" ${TO_BIN:+"$TO_BIN" "$TIMEOUT"} codex --search exec -s workspace-write -C "$WORKDIR" \
        --skip-git-repo-check --ephemeral "$PROMPT" >"$WORKDIR/.da-codex.log" 2>&1 ;;
    opencode)
      DA_OUT="$OUT" ${TO_BIN:+"$TO_BIN" "$TIMEOUT"} opencode run --dir "$WORKDIR" \
        ${DA_OPENCODE_MODEL:+-m "$DA_OPENCODE_MODEL"} "$PROMPT" >"$WORKDIR/.da-opencode.log" 2>&1 ;;
    *) return 1 ;;
  esac
  pack_ok
}

for eng in ${DA_ENGINES:-codex opencode}; do
  if run_engine "$eng"; then
    printf '\nEngine: %s\n' "$eng" >>"$OUT"
    echo "ENGINE=$eng OUT=$OUT"
    exit 0
  fi
  echo "engine $eng unavailable or pack invalid (log: $WORKDIR/.da-$eng.log)" >&2
done
fallback no_second_model
