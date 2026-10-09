#!/usr/bin/env bash
# 定稿前報告自檢：引用結構（validate_report.py）＋禁詞 grep（forbidden-words.md SSOT）。
# 任一段 FAIL → 整體非 0。用法：check_report.sh <report.md> [--mode competitor|vendor-dd|academic] | --selftest
# --mode 只用來標示報告類型；來源總數／正文字數下限已於 2026-09-16 刪除（見 issue.md）。
# --lang 預設 zh-hans：正文疑似繁體即 FAIL（報告規定簡體中文）；使用者指定其他語言時用 --lang any。
# --answer-map <audit/answer-map.md>：帳本必答題＋核心問題 → 報告原句對照；帳本取 $RESEARCH_BUDGET 或 ./.research-budget.json。
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FW="$SCRIPT_DIR/../references/forbidden-words.md"

extract_forbidden() {
  # 只取 fenced ```text ``` 區塊（forbidden-words 的 SSOT），剔除空行與前導空白
  awk '/^```text$/{f=1;next} /^```$/{f=0} f' "$FW" \
    | grep -v '^\s*$' \
    | sed 's/[[:space:]]*$//'
}

# 檢索軌跡閘門：否定句（未檢索到／未能確認／未命中…）是主張，不是免責。
# 沒有可出示的檢索軌跡，第三方無從複驗，等於用措辭冒充結論。
# ponytail: 只驗「有否定句就必須有附軌跡章節且含 URL」，不做逐句對應；要逐句綁定再說。
NEG_RE='未檢索到|未检索到|未能確認|未能确认|未命中|未查到|未覆蓋|未覆盖|未見登錄|未见登录|無公開|无公开|未找到'

trail_gate() {
  local report="$1" negs
  negs=$(grep -nE "$NEG_RE" "$report" 2>/dev/null || true)
  if [ -z "$negs" ]; then
    echo "OK: no negative claim"
    return 0
  fi
  # awk 而非 sed：BSD sed 的 BRE 不支援 \| 交替，抓不到章節就會誤判成無軌跡
  if awk '/^#+.*(檢索軌跡|检索轨迹)/{f=1} f' "$report" | grep -q 'http'; then
    echo "OK: $(printf '%s\n' "$negs" | grep -c . | tr -d ' ') negative claim(s) backed by a 檢索軌跡 section"
    return 0
  fi
  echo "FAIL: 報告有否定句但缺「檢索軌跡」章節（或該章節無 URL）——否定主張須附查詢詞與走訪連結"
  printf '%s\n' "$negs" | head -10
  return 1
}

selftest() {
  # 用內建含禁詞樣本確認清單擷取正常：樣本必須命中至少一詞。
  # 三個樣本各自必須命中；任一漏掉即清單失效。
  local samples=("此項待跟內·部確認" "第二轮补强结果" "a fetch b" "该口径[待核實]") hits ok=0
  samples[0]="${samples[0]/·/}"
  for s in "${samples[@]}"; do
    hits=$(extract_forbidden | while IFS= read -r pat; do grep -qE "$pat" <<<"$s" && echo "$pat"; done)
    if [ -z "$hits" ]; then
      echo "SELFTEST FAIL: sample not caught: $s" >&2
      return 1
    fi
    ok=$((ok+1))
  done
  # 不得誤中的自然詞
  local clean="background prefetch subagentless 2024-03 1403 roundabout"
  hits=$(extract_forbidden | while IFS= read -r pat; do grep -qE "$pat" <<<"$clean" && echo "$pat"; done)
  if [ -n "$hits" ]; then
    echo "SELFTEST FAIL: false positive on clean sample: $hits" >&2
    return 1
  fi
  # 規範自檢：本 repo 格式文件的正規章名不得命中禁詞，
  # 否則「照格式寫章名」與「過禁詞閘門」在定義上不可能同時成立。
  local fmt heads hitlines=""
  for fmt in "$SCRIPT_DIR/../references/report-format.md" \
             "$SCRIPT_DIR/../references/report-format-vendor-dd.md"; do
    [ -f "$fmt" ] || continue
    heads=$(grep -E '^#{2,3} ' "$fmt" || true)
    [ -n "$heads" ] || continue
    while IFS= read -r pat; do
      [ -n "$pat" ] || continue
      hit=$(printf '%s\n' "$heads" | grep -nE "$pat" | head -1 || true)
      [ -n "$hit" ] && hitlines="$hitlines
  $(basename "$fmt") [$pat] <- $hit"
    done < <(extract_forbidden)
  done
  if [ -n "$hitlines" ]; then
    echo "SELFTEST FAIL: 格式文件的正規章名命中禁詞（規範互斥，兩邊須擇一改）:$hitlines" >&2
    return 1
  fi
  # 檢索軌跡閘門自檢：無軌跡的否定句必須被擋，補上軌跡章節後必須放行。
  local tmpd tmpr
  tmpd="$(mktemp -d "${TMPDIR:-/tmp}/checkrep.XXXXXX")"
  tmpr="$tmpd/r.md"
  printf '# t\n\n本次已查阅的公开来源未能确认该事项。\n' > "$tmpr"
  if trail_gate "$tmpr" >/dev/null 2>&1; then
    echo "SELFTEST FAIL: 無軌跡的否定句未被擋下" >&2; rm -rf "$tmpd"; return 1
  fi
  printf '\n## 附录：检索轨迹\n\n| 查询词 | 走访 | 结果 |\n|---|---|---|\n| x | https://example.com | 0 |\n' >> "$tmpr"
  if ! trail_gate "$tmpr" >/dev/null 2>&1; then
    echo "SELFTEST FAIL: 補上檢索軌跡後仍未放行" >&2; rm -rf "$tmpd"; return 1
  fi
  printf '# t2\n\n全部主張皆有來源。\n' > "$tmpr"
  if ! trail_gate "$tmpr" >/dev/null 2>&1; then
    echo "SELFTEST FAIL: 無否定句的報告被誤擋" >&2; rm -rf "$tmpd"; return 1
  fi
  rm -rf "$tmpd"
  if [ "$ok" -eq "${#samples[@]}" ]; then
    echo "SELFTEST PASS: forbidden-word extraction live ($ok samples caught, 0 false positives)"
    return 0
  fi
  echo "SELFTEST FAIL: forbidden-word list broke (no hit in known-bad sample)" >&2
  return 1
}

if [ "${1:-}" = "--selftest" ]; then
  selftest
  exit $?
fi

REPORT="${1:?usage: check_report.sh <report.md> [--mode competitor|vendor-dd|academic] [--lang zh-hans|any] [--answer-map <map.md>]}"
shift
MODE=""
LANG_RULE="zh-hans"
ANSWER_MAP=""
while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE="${2:-}"; shift 2 ;;
    --lang) LANG_RULE="${2:-}"; shift 2 ;;
    --answer-map) ANSWER_MAP="${2:-}"; shift 2 ;;
    *) echo "usage: check_report.sh <report.md> [--mode competitor|vendor-dd|academic] [--lang zh-hans|any] [--answer-map <map.md>]" >&2; exit 2 ;;
  esac
done
case "$LANG_RULE" in zh-hans|any) ;; *) echo "usage: unknown --lang '$LANG_RULE' (zh-hans|any)" >&2; exit 2 ;; esac
FLOORS=(--lang "$LANG_RULE")
case "$MODE" in
  "") ;;
  competitor|vendor-dd|academic) ;;
  *) echo "usage: unknown --mode '$MODE' (competitor|vendor-dd|academic)" >&2; exit 2 ;;
esac
if [ ! -f "$REPORT" ]; then
  echo "FAIL: report not found: $REPORT" >&2
  exit 2
fi
if [ -n "$ANSWER_MAP" ]; then
  BUDGET_FILE="${RESEARCH_BUDGET:-./.research-budget.json}"
  for f in "$ANSWER_MAP" "$BUDGET_FILE"; do
    [ -f "$f" ] || { echo "FAIL: not found: $f" >&2; exit 2; }
  done
  FLOORS+=(--answer-map "$ANSWER_MAP" --budget "$BUDGET_FILE")
fi

# 1) 引用結構（＋依 mode 的深度門檻）
python3 "$SCRIPT_DIR/validate_report.py" "$REPORT" ${FLOORS[@]+"${FLOORS[@]}"}
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "STRUCTURE CAUGHT: validate_report.py returned $rc" >&2
  exit 1
fi

# 2) 禁詞 grep（每詞命中即列行號）
echo "== forbidden-words scan =="
bad=0
while IFS= read -r pat; do
  [ -n "$pat" ] || continue
  hits=$(grep -nE "$pat" "$REPORT" 2>/dev/null || true)
  if [ -n "$hits" ]; then
    # 每行命中只印 pattern＋第一個行號，避免同 pattern 重複刷屏
    echo "FAIL: line $(printf '%s' "$hits" | head -1 | cut -d: -f1) pattern [$pat]"
    bad=1
  fi
done < <(extract_forbidden)

if [ "$bad" -ne 0 ]; then
  echo "FORBIDDEN CAUGHT" >&2
  exit 1
fi

# 3) 結論收斂閘門（FAIL，硬阻斷）：S1「未檢索到/未見登錄」與「需複核」稀釋並存＝偽查實。
#    名冊查無是硬負面證據，配「中/低」或「需以正式文件複核」即未據實升等，判未定稿。
echo "== verdict-leak scan =="
if grep -nE "未檢索到|未見登錄|未检索到|未见登录" "$REPORT" >/dev/null 2>&1; then
  if grep -nE "需以正式文件複核|需以正式文件复核|需以.*複核|需以.*复核|待核實|待核实" "$REPORT" >/dev/null 2>&1; then
    echo "FAIL: S1 名冊查無與「需複核/待核實」並存——負面核實結果被稀釋，未據實升等（見 evidence-standards.md「風險結論映射」）"
    exit 1
  fi
fi

# 4) 檢索軌跡閘門（FAIL，硬阻斷）
echo "== negative-claim trail scan =="
trail_gate "$REPORT" || exit 1

echo "PASS: structure + forbidden-words scan clean"
exit 0