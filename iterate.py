#!/usr/bin/env python3
"""
文明OS 迭代脚本 v0.2.x（多文件版）
扫描主页和nodes/目录下所有含💬评论的文件→逐一调用模型整合→更新文件→git commit→push
"""

import requests, json, subprocess, sys, os, re
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def generate_timestamps():
    """生成ISO时间戳和宿主风格版本标识（created_at用UTC毫秒Z；version_tag用北京时间+08:00）"""
    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    ts_iso = now_utc.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now_utc.microsecond // 1000:03d}Z'
    ts_ver = datetime.now(timezone(timedelta(hours=8))).strftime('V%Y%m%d%H%M%S+')
    return ts_iso, ts_ver


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


def get_immutable_core():
    """提取 system-prompt 不可变核心区（IMMUTABLE CORE 与 ITERABLE LAYER 标记之间）内容"""
    try:
        t = Path(PROMPT_FILE).read_text(encoding="utf-8")
    except Exception:
        return None
    start = t.find('IMMUTABLE CORE')
    end = t.find('ITERABLE LAYER')
    if start == -1 or end == -1:
        return None
    return t[start:end]


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
    core_snapshot = get_immutable_core()  # 不可变核心区快照（防迭代旁路污染）

    # 并行模式（默认4并行：sglang max-running-requests=16 实测4路真并行无排队，功耗与2路相同；--parallel N 可覆盖，0/1=串行）
    parallel = 4
    if '--parallel' in sys.argv:
        try:
            parallel = max(1, int(sys.argv[sys.argv.index('--parallel') + 1]))
        except (IndexError, ValueError):
            parallel = 3
        print(f" 并行模式：{parallel} 个工作线程")

    # 收集所有需要处理的文件（主页+nodes/下所有.md）
    candidates = [Path(HUB_FILE)]
    nodes_path = Path(NODES_DIR)
    if nodes_path.exists():
        candidates += sorted(nodes_path.rglob("*.md"))

    print(f"[扫描] 共{len(candidates)}个文件")

    def process_file(fpath):
        """单文件完整处理流程；返回 (更新路径|None, 日志行)。写回各自文件，线程安全。"""
        content = read_file(str(fpath))
        if not has_comments(content):
            return None, f"  跳过（无评论）: {fpath.name}"
        ts_inner = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup = Path(ITERATIONS_DIR) / f"{fpath.stem}_{ts_inner}.md"
        write_file(str(backup), content)
        try:
            new_content = call_model(system_prompt, content)
        except Exception as e:
            return None, f" ❌ 模型调用失败: {fpath.name}: {e}"
        if not validate(new_content, str(fpath)):
            err_path = Path(ITERATIONS_DIR) / f"failed_{fpath.stem}_{ts_inner}.md"
            write_file(str(err_path), new_content)
            return None, f" ⚠️ 校验失败，原文件保持不变: {fpath.name}"
        if len(new_content.encode('utf-8')) < len(content.encode('utf-8')) * 0.5:
            err_path = Path(ITERATIONS_DIR) / f"failed_{fpath.stem}_{ts_inner}.md"
            write_file(str(err_path), new_content)
            return None, f" ⚠️ 体积缩水超半，原文件保持不变: {fpath.name}"
        write_file(str(fpath), format_fix(new_content))
        return str(fpath), f" ✅ 处理完成: {fpath.name}"

    changed_files = []
    if parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {executor.submit(process_file, f): f for f in candidates}
            for future in as_completed(futures):
                path, msg = future.result()
                print(msg, flush=True)
                if path:
                    changed_files.append(path)
    else:
        for fpath in candidates:
            path, msg = process_file(fpath)
            print(msg, flush=True)
            if path:
                changed_files.append(path)

    if changed_files:
        # 不可变核心区守卫：提交前复核 system-prompt 标记区内容与启动快照一致
        if core_snapshot is not None and get_immutable_core() != core_snapshot:
            print(" ❌ 守卫触发：system-prompt 不可变核心区在本轮迭代中被改动，已回滚该文件，提交中止")
            subprocess.run(["git", "checkout", "--", PROMPT_FILE], capture_output=True)
            sys.exit(1)
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
