#!/bin/bash
# 文明OS 状态快查（第23阶段睡眠守护交接件·宿主醒来一键跑）
echo "====== 文明OS 状态快查 $(date '+%Y-%m-%d %H:%M') ======"

echo ""
echo "【后台任务】"
if pgrep -f "[r]eplay23.py" >/dev/null; then
  echo " 重放在线 PID=$(pgrep -f '[r]eplay23.py' | head -1)（当前件: $(tail -2 /tmp/civ-replay23.log | grep -a '^\[' | tail -1 | cut -c1-60)）"
else
  grep -aq REPLAY23-DONE /tmp/civ-replay23.log 2>/dev/null && echo " 后台重放：已完成（REPLAY23-DONE）" || echo " 后台重放：未运行（查 /tmp/civ-replay23.log）"
fi
echo " 进度: $(grep -ac '✅' /tmp/civ-replay23.log 2>/dev/null)/35"

echo ""
echo "【守护日志（今日）】"
tail -10 /tmp/guardian_civos.log 2>/dev/null || echo " 无守护日志"

echo ""
echo "【重放失败件（如有）】"
grep -a "FAIL|" /tmp/civ-replay23.log 2>/dev/null || echo " （无）"

echo ""
echo "【私有版激发总量】"
grep -ra "^> 💬" /home/v01/CUR-Agent/knowledge-base/obsidian-import/文明OS项目簇/私有版节点/ | wc -l

echo ""
echo "【公共版状态】"
cd /home/v01/CUR-Agent/PROJECTS/civ-os/ || exit 1
echo " HEAD: $(git rev-parse --short HEAD)"
echo " 节点文件: $(find nodes/ -name '*.md' | wc -l)个"

echo ""
echo "【HUB最新5行】"
tail -5 /home/v01/CUR-Agent/knowledge-base/obsidian-import/文明OS项目簇/HUB-文明OS簇.md

echo ""
echo "【OpenClaw cron 守门】"
echo " 12:40 进度登记(38321cdb) + 次日08:00 终态回写(cdf7ed04) — 见 cron list"
echo ""
echo "====== 检查完毕 ======"
