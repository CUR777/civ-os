#!/bin/bash
# deliver-check.sh v1p · 交付链接硬闸（公共化版，源=私有侧 1016 #ZZ-B55-LINKGATE-1016 五检闸）
# 用途=一切 viewer/report 链接投出前的唯一出口闸门。退出码≠0=禁投。
# 用法: deliver-check.sh <静态目录文件名>
#       deliver-check.sh --url '<完整URL>'   （复核既有 URL）
# 必需环境变量（禁硬编码本机地址）:
#   SGDELIVER_BASE  例 http://<host>:<port>/media/sgdeliver
#   SGDELIVER_DIR   静态目录绝对路径（文件真实落盘处）
set -u
BASE="${SGDELIVER_BASE:?需设 SGDELIVER_BASE}"
DIR="${SGDELIVER_DIR:?需设 SGDELIVER_DIR}"
FAILS=0
say(){ echo "[$1] $2"; if [ "$1" = FAIL ]; then FAILS=$((FAILS+1)); fi; return 0; }
if [ "${1:-}" = "--url" ]; then
  U="${2:-}"
  case "$U" in *%25*) say FAIL "双重编码 %25=***";; esac
  C=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$U")
  [ "$C" = 200 ] && say OK "URL 200" || say FAIL "URL HTTP=$C"
  [ $FAILS -eq 0 ] && echo GATE-PASS || { echo "GATE-FAIL(禁投)"; exit 1; }
  exit 0
fi
FN="${1:-}"
[ -z "$FN" ] && { echo "用法: $0 <文件名> | --url <URL>"; exit 2; }
[ -f "$DIR/$FN" ] && say OK "文件在位 ($(wc -c <"$DIR/$FN")B)" || say FAIL "文件不存在=$FN（先落盘再组链=防假交付）"
ENC=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$FN")
echo "$ENC" | grep -q '%25' && say FAIL "编码产出含 %25（上游已双编码）"
C1=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/$ENC")
[ "$C1" = 200 ] && say OK "文件直链 200" || say FAIL "文件直链 HTTP=$C1"
U="$BASE/viewer.html?f=$ENC"
C2=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$U")
[ "$C2" = 200 ] && say OK "viewer 壳 200" || say FAIL "viewer HTTP=$C2"
curl -s --max-time 10 "$BASE/viewer.html" | grep -q 'marked' && say OK "壳含渲染腿" || say FAIL "壳页缺渲染腿"
if [ $FAILS -eq 0 ]; then echo GATE-PASS; echo "FINAL_URL<<$U>>"; else echo "GATE-FAIL(禁投)"; exit 1; fi

# evidence: 来源=1016 #ZZ-B55-LINKGATE-1016 假交付再犯案加固；五检闸 1016 实测 GATE-PASS rc=0 + 闸测闸自修案（say() bug 首跑拦出）@2026-10-16
