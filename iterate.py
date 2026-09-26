#!/usr/bin/env python3
"""
文明OS 迭代脚本 v0.0.1
读取当前版本 civ-os.md + 系统提示词 → 调用本地Ollama模型 → 输出新版本 → git commit
"""

import requests
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ═══ 配置 ═══
MODEL = "pennyroyal"  # sglang 现役模型名（=Q3.8 flash 125B，/v1/models 实测返回 id=pennyroyal，ctx 524288）
API_URL = "http://127.0.0.1:8001/v1/chat/completions"  # sglang OpenAI兼容端点（直连口，无鉴权；8002=TTL会话代理口，一次性批量调用按库内先例走8001）
MAIN_FILE = "civ-os.md"  # 主文件
PROMPT_FILE = "system-prompt.md"  # 系统提示词文件
ITERATIONS_DIR = "iterations"  # 历史版本存放目录
TIMEOUT = 900  # API超时秒数（15分钟，大模型推理可能较慢）
TEMPERATURE = 0.3  # 生成温度（偏低=更稳定）
MAX_TOKENS = 32768  # 最大生成token数


def read_file(path: str) -> str:
    """读取文件内容"""
    return Path(path).read_text(encoding="utf-8")


def write_file(path: str, content: str):
    """写入文件内容"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


def call_model(system_prompt: str, user_content: str) -> str:
    """调用 sglang OpenAI兼容 chat/completions API"""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "max_tokens": MAX_TOKENS,   # OpenAI格式字段（原Ollama options.num_predict）
        "temperature": TEMPERATURE
    }
    # 注：Q3.8 on sglang 思考通道 reasoning_content 无法经参数关闭（chat_template_kwargs.thinking /
    # /no_think 实测均仍返回思考文本），但正文落在 message.content，本脚本只取 content，管道不受影响。
    print(f" → 调用模型 {MODEL}（sglang@8001），请等待...")
    resp = requests.post(API_URL, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    result = resp.json()
    return result["choices"][0]["message"]["content"]


def git_push():
    """推送到GitHub远程仓库（失败不中断迭代，只记录警告）"""
    result = subprocess.run(
        ["git", "push", "origin", "master"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(" ✓ GitHub推送成功 ✅")
    else:
        print(f" ⚠️ GitHub推送失败（本地commit已保存）: {result.stderr.strip()}")


def git_commit(message: str):
    """执行git add + commit"""
    subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f" ✓ Git提交成功: {message}")
    else:
        print(f" ○ Git提交跳过（可能无变更）: {result.stderr.strip()}")


def main():
    """主迭代流程"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'='*60}")
    print(f"文明OS 迭代开始 — {timestamp}")
    print(f"{'='*60}\n")

    # 1. 读取当前版本和系统提示词
    print("[1/5] 读取文件...")
    current_content = read_file(MAIN_FILE)
    system_prompt = read_file(PROMPT_FILE)
    print(f" 主文件: {len(current_content)} 字符")
    print(f" 系统提示词: {len(system_prompt)} 字符")

    # 2. 检查是否有用户评论
    has_comments = "> 💬 " in current_content or "[已读]" in current_content
    if not has_comments:
        print("\n ⚠️ 未检测到用户评论（> 💬 标记），本次迭代将执行基础优化。")

    # 3. 备份当前版本
    print(f"\n[2/5] 备份当前版本...")
    backup_path = f"{ITERATIONS_DIR}/v_{timestamp}.md"
    write_file(backup_path, current_content)
    print(f" → 已备份至: {backup_path}")

    # 4. 调用模型迭代
    print(f"\n[3/5] 调用模型迭代...")
    try:
        new_content = call_model(system_prompt, current_content)
    except requests.exceptions.Timeout:
        print(" ❌ 模型调用超时（超过15分钟），本次迭代中止。")
        sys.exit(1)
    except Exception as e:
        print(f" ❌ 模型调用失败: {e}")
        sys.exit(1)

    print(f" → 模型输出: {len(new_content)} 字符")

    # 5. 基础校验
    print(f"\n[4/5] 基础校验...")
    checks_passed = True

    if "公理Ⅰ" not in new_content:
        print(" ❌ 校验失败：公理Ⅰ丢失")
        checks_passed = False
    if "公理Ⅱ" not in new_content:
        print(" ❌ 校验失败：公理Ⅱ丢失")
        checks_passed = False
    if "公理Ⅲ" not in new_content:
        print(" ❌ 校验失败：公理Ⅲ丢失")
        checks_passed = False
    if "元流程" not in new_content:
        print(" ❌ 校验失败：元流程区丢失")
        checks_passed = False
    if "停止迭代" in new_content and "不得" not in new_content:
        print(" ⚠️ 警告：输出中包含'停止迭代'但缺少否定语境，请人工复查")
    if len(new_content) < len(current_content) * 0.5:
        print(f" ⚠️ 警告：新版本字数({len(new_content)})不足旧版本({len(current_content)})的50%，可能有内容丢失")

    if not checks_passed:
        print("\n ❌ 校验未通过，新版本不写入。原版本保持不变。")
        print(f" → 模型原始输出已保存至: {ITERATIONS_DIR}/failed_{timestamp}.md")
        write_file(f"{ITERATIONS_DIR}/failed_{timestamp}.md", new_content)
        sys.exit(1)

    print(" ✓ 基础校验通过")

    # 6. 写入新版本 + git commit
    print(f"\n[5/5] 写入新版本并提交...")
    # 程序化格式后处理：去除首部多余空行，确保末尾有且只有一个换行符
    new_content = new_content.lstrip('\n')  # 去掉开头所有多余空行
    new_content = new_content.rstrip('\n') + '\n'  # 末尾保留且只保留一个换行
    print(" ✓ 格式后处理完成（首部空行已清理，末尾换行已规范）")
    write_file(MAIN_FILE, new_content)
    git_commit(f"迭代 {timestamp}")
    git_push()

    print(f"\n{'='*60}")
    print(f"文明OS 迭代完成 — {datetime.now().strftime('%Y%m%d_%H%M%S')}")
    print(f" 旧版本备份: {backup_path}")
    print(f" 新版本: {MAIN_FILE}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
