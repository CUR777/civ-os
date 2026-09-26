#!/usr/bin/env python3
"""
文明OS 迭代脚本 v0.2.x（多文件版）
扫描主页和nodes/目录下所有含💬评论的文件→逐一调用模型整合→更新文件→git commit→push
"""

import requests, json, subprocess, sys, os, re
from datetime import datetime
from pathlib import Path

MODEL = "pennyroyal"
API_URL = "http://127.0.0.1:8001/v1/chat/completions"
HUB_FILE = "文明OS-主页.md"
NODES_DIR = "nodes"
PROMPT_FILE = "system-prompt.md"
ITERATIONS_DIR = "iterations"
TIMEOUT = 900
TEMPERATURE = 0.3
MAX_TOKENS = 32768
CHUNK_THRESHOLD_BYTES = 200000


def read_file(path):
    return Path(path).read_text(encoding="utf-8")


def write_file(path, content):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


def call_model(system_prompt, user_content):
    # OpenAI兼容字段（sglang端点不识别Ollama的options段，必须用max_tokens/temperature顶层字段）
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "stream": False,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE
    }
    resp = requests.post(API_URL, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def has_comments(content):
    # 行首匹配（真实评论均以「> 💬 」起行）；避免主页/README参与说明中的内联示例 `> 💬 …` 误触发每轮白烧模型调用
    return any(line.startswith("> \U0001f4ac ") or line.rstrip() == "> \U0001f4ac" for line in content.splitlines())


def git_commit(message):
    subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
    result = subprocess.run(["git", "commit", "-m", message],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print(f" ✓ Git提交成功: {message}")
    else:
        print(f" ○ Git提交跳过（无变更）: {result.stderr.strip()}")


def git_push():
    result = subprocess.run(["git", "push", "origin", "master"],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print(" ✓ GitHub推送成功 ✅")
    else:
        print(f" ⚠️ GitHub推送失败（本地commit已保存）: {result.stderr.strip()}")


def validate(content, filename=""):
    checks = [
        ("公理Ⅰ" in content or "节点" in filename, "公理Ⅰ或节点内容"),
        (len(content) > 100, "内容不为空"),
    ]
    if HUB_FILE in filename or "主页" in filename:
        checks = [
            ("公理Ⅰ" in content, "公理Ⅰ"),
            ("公理Ⅱ" in content, "公理Ⅱ"),
            ("公理Ⅲ" in content, "公理Ⅲ"),
            ("元流程" in content, "元流程"),
        ]
    for ok, name in checks:
        if not ok:
            print(f" ❌ 校验失败：{name}丢失（{filename}）")
            return False
    return True


def format_fix(content):
    content = content.lstrip("\n")
    content = content.rstrip("\n") + "\n"
    return content


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'='*60}")
    print(f"文明OS 迭代开始 — {ts}")
    print(f"{'='*60}\n")

    system_prompt = read_file(PROMPT_FILE)
    changed_files = []

    # 收集所有需要处理的文件（主页+nodes/下所有.md）
    candidates = [Path(HUB_FILE)]
    nodes_path = Path(NODES_DIR)
    if nodes_path.exists():
        candidates += sorted(nodes_path.rglob("*.md"))

    print(f"[扫描] 共{len(candidates)}个文件")

    for fpath in candidates:
        content = read_file(str(fpath))
        if not has_comments(content):
            print(f"  跳过（无评论）: {fpath.name}")
            continue

        print(f"\n[处理] {fpath.name} （{len(content.encode())}字节）")
        # 备份
        backup = Path(ITERATIONS_DIR) / f"{fpath.stem}_{ts}.md"
        write_file(str(backup), content)

        # 调用模型
        print("  调用模型...")
        try:
            new_content = call_model(system_prompt, content)
        except Exception as e:
            print(f" ❌ 模型调用失败: {e}")
            continue

        # 校验
        if not validate(new_content, str(fpath)):
            err_path = Path(ITERATIONS_DIR) / f"failed_{fpath.stem}_{ts}.md"
            write_file(str(err_path), new_content)
            print("  校验失败，跳过此文件，原文件保持不变")
            continue

        # 格式修正
        new_content = format_fix(new_content)
        write_file(str(fpath), new_content)
        changed_files.append(str(fpath))
        print(" ✅ 处理完成")

    if changed_files:
        print(f"\n[提交] {len(changed_files)}个文件已更新")
        git_commit(f"迭代 {ts}")
        git_push()
    else:
        print("\n[跳过提交] 无文件变更")

    print(f"\n{'='*60}")
    print(f"文明OS 迭代完成 — {datetime.now().strftime('%Y%m%d_%H%M%S')}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
