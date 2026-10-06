#!/bin/bash
# 文明OS 开机自动同步脚本 v2 (20260927 补：sglang预热3-4min避让 + 联合查询时主动核验)
# 职责：塔机每次开机时自动检测云端是否领先，落后则快进，确保Obsidian显示与GitHub一致
# 设计：与 monthly_external_sync.sh 互补（月度兜底 vs 每次开机即时）；v2 新增 sglang 预热避让与网络满足性自检
# 用法：
# 开机自启： bash scripts/sync_on_boot.sh &
# 龙虾主动核验：bash scripts/sync_on_boot.sh --query-check (用于联合查询 CUR-OS + civ-os 前)
# 手动： bash scripts/sync_on_boot.sh --force
LOG="/tmp/civos_sync_boot.log"
REPO="/home/v01/CUR-Agent/PROJECTS/civ-os"
if [ -n "$CIVOS_REPO" ]; then REPO="$CIVOS_REPO"; fi
if [ ! -d "$REPO/.git" ]; then REPO="$(cd "$(dirname "$0")/.." && pwd)"; fi
MODE="${1:-boot}"
echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot v2] 模式=$MODE repo=$REPO" | tee -a "$LOG"
cd "$REPO" || { echo "仓库路径不存在: $REPO" | tee -a "$LOG"; exit 1; }

# --- 0. sglang 预热避让 (仅 boot 模式) ---
if [ "$MODE" = "boot" ]; then
  SGLANG_URL="http://127.0.0.1:8001/v1/models"
  WAIT_SEC=240
  INTERVAL=10
  echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 等待 sglang 就绪 (最长 ${WAIT_SEC}s, 每${INTERVAL}s探活)..." | tee -a "$LOG"
  for i in $(seq 1 $((WAIT_SEC/INTERVAL))); do
    if curl -s --max-time 3 "$SGLANG_URL" >/dev/null 2>&1; then
      echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] sglang 已就绪 (用时约 $((i*INTERVAL))s)" | tee -a "$LOG"
      break
    fi
    if pgrep -f "iterate.py" >/dev/null 2>&1; then
      echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 检测到 iterate.py 运行中，退让 ${INTERVAL}s..." | tee -a "$LOG"
    fi
    sleep $INTERVAL
    if [ "$i" -eq "$((WAIT_SEC/INTERVAL))" ]; then
      echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] sglang 未在 ${WAIT_SEC}s 内就绪，仍继续执行 git 同步（仅fetch/pull，不依赖模型）" | tee -a "$LOG"
    fi
  done
fi

# --- 1. 网络满足性自检 ---
# 细节已抽象：按本地文档中网络满足性的自适应方式探活与提示，具体补充由智能体按本地配置执行
check_network() {
  if curl -s --max-time 5 -I https://github.com >/dev/null 2>&1; then
    echo "ok"
  elif ping -c1 -W3 8.8.8.8 >/dev/null 2>&1; then
    echo "ok-ping"
  else
    echo "offline"
  fi
}
NET=$(check_network)
echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 网络探活: $NET" | tee -a "$LOG"
if [ "$NET" = "offline" ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 网络未满足，提示智能体按本地配置补充网络满足性后重试（脚本本次不强行补充，避免误触）" | tee -a "$LOG"
  sleep 3
  NET=$(check_network)
  if [ "$NET" = "offline" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 仍离线，退出本次同步，下次查询时再试" | tee -a "$LOG"
    exit 0
  fi
fi

# --- 2. 云端探活与比对 ---
if ! git fetch origin >>"$LOG" 2>&1; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] git fetch 失败，保留本地版本" | tee -a "$LOG"
  exit 0
fi
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master 2>/dev/null || echo "unknown")
BASE=$(git merge-base HEAD origin/master 2>/dev/null || echo "none")
echo " LOCAL=$(git rev-parse --short HEAD) REMOTE=$(git rev-parse --short origin/master 2>/dev/null || echo "$REMOTE") BASE=$(git rev-parse --short "$BASE" 2>/dev/null || echo none)" | tee -a "$LOG"

# --- 3. 决策：是否拉取 ---
should_pull="yes"
REASON="云端领先且可快进"
if [ "$LOCAL" = "$REMOTE" ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 已是最新，无需同步" | tee -a "$LOG"
  echo "[同步: 云端已最新 $(git rev-parse --short HEAD)]"
  exit 0
fi
if [ "$(git rev-parse "$BASE" 2>/dev/null)" = "$LOCAL" ]; then
  if [ -n "$(git status --porcelain)" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 本地有未提交改动（含可能的 >💬），本次不自动 pull，留待查询时主动核验或手动处理" | tee -a "$LOG"
    git status --short | tee -a "$LOG"
    should_pull="defer"
    REASON="本地有未提交改动，尊重 append-only， defer 到查询时或手动"
  fi
  if [ "$should_pull" = "yes" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 判定：$REASON，执行 pull --ff-only" | tee -a "$LOG"
    if git pull --ff-only origin master >>"$LOG" 2>&1; then
      echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 快进成功，新HEAD=$(git rev-parse --short HEAD)" | tee -a "$LOG"
      echo "✅ 已从云端同步到 $(git rev-parse --short HEAD)"
    else
      echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 快进失败，请手动处理: git status" | tee -a "$LOG"
      git status --short | tee -a "$LOG"
    fi
  else
    echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 本次 defer，不执行 pull。将在下次联合查询时由龙虾主动核验 (scripts/sync_on_boot.sh --query-check)" | tee -a "$LOG"
    echo "[同步: 已defer因$REASON]"
  fi
elif [ "$(git rev-parse "$BASE" 2>/dev/null)" = "$REMOTE" ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 本地领先云端，无需拉取（本地待push）" | tee -a "$LOG"
else
  echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] 分叉：本地与云端均有新提交，需手动合并" | tee -a "$LOG"
  git log --oneline --graph --all -5 | tee -a "$LOG"
fi

if [ "$MODE" = "--query-check" ]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') [sync_on_boot] query-check 完成，已确保本次回答基于最新云端（如已拉取）" | tee -a "$LOG"
fi
exit 0
