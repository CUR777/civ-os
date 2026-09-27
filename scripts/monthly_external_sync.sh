#!/bin/bash
# 文明OS 月度外部评论整理脚本
# 逻辑：每月1号执行；若跨月未执行（如未开机），下一次09:00检查时自动补跑
# 手动触发：bash scripts/monthly_external_sync.sh manual

LOG="/tmp/civos_monthly.log"
STATE_FILE="/home/v01/CUR-Agent/PROJECTS/civ-os/.monthly_sync_state"
MANUAL=${1:-""}

echo "$(date '+%Y-%m-%d %H:%M') 月度外部同步检查" >> $LOG

TODAY=$(date '+%Y-%m')
LAST_RUN=$(cat "$STATE_FILE" 2>/dev/null || echo "never")

if [ "$MANUAL" = "manual" ]; then
  echo "$(date '+%Y-%m-%d %H:%M') 手动触发，强制执行" >> $LOG
  SHOULD_RUN=true
elif [ "$LAST_RUN" = "$TODAY" ]; then
  echo "$(date '+%Y-%m-%d %H:%M') 本月已执行（$LAST_RUN），跳过" >> $LOG
  exit 0
else
  SHOULD_RUN=true
  if [ "$LAST_RUN" != "never" ]; then
    echo "$(date '+%Y-%m-%d %H:%M') 检测到跨月未执行（上次：$LAST_RUN），补跑" >> $LOG
  fi
fi

if [ "$SHOULD_RUN" = "true" ]; then
  echo "$(date '+%Y-%m-%d %H:%M') 开始月度外部评论整理..." >> $LOG

  cd /home/v01/CUR-Agent/PROJECTS/civ-os/ || exit 1

  # 1. 拉取GitHub最新状态（只fetch不动工作区）
  git fetch origin >> $LOG 2>&1
  git status --short >> $LOG 2>&1

  # 2. 外部PR/反馈检查（GitHub API）
  EXTERNAL=$(curl -s --max-time 20 "https://api.github.com/repos/CUR777/civ-os/pulls?state=open" \
    | python3 -c "import sys,json; prs=json.load(sys.stdin); print(f'开放PR：{len(prs)}个')" 2>/dev/null \
    || echo "GitHub API暂时不可达")
  ISSUES=$(curl -s --max-time 20 "https://api.github.com/repos/CUR777/civ-os/issues?state=open" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'开放issue：{len(d)}个')" 2>/dev/null || echo "")
  echo "$(date '+%Y-%m-%d %H:%M') $EXTERNAL ${ISSUES}" >> $LOG

  # 3. 私有版积累量统计（实测口径）
  PRIV_COUNT=$(grep -ra "^> 💬" \
    /home/v01/CUR-Agent/knowledge-base/obsidian-import/文明OS项目簇/私有版节点/ \
    2>/dev/null | wc -l)
  echo "$(date '+%Y-%m-%d %H:%M') 私有版当前激发量：${PRIV_COUNT}条" >> $LOG

  # 4. 更新HUB记录
  cat >> "/home/v01/CUR-Agent/knowledge-base/obsidian-import/文明OS项目簇/HUB-文明OS簇.md" << HUBEOF

## 月度外部同步（$(date '+%Y年%m月')）
- 执行时间：$(date '+%Y-%m-%d %H:%M')
- 触发方式：$([ "$MANUAL" = "manual" ] && echo "手动" || echo "定时（含跨月补跑）")
- GitHub状态：${EXTERNAL} ${ISSUES}
- 私有版激发量：${PRIV_COUNT}条
- 待办：检查是否有值得通用化提交公共版的内容（外部评论一律中性化后进公共版=隔离红线）
HUBEOF

  # 5. 记录本次执行月份
  echo "$TODAY" > "$STATE_FILE"
  echo "$(date '+%Y-%m-%d %H:%M') 月度同步完成，状态已记录（$TODAY）" >> $LOG
fi
