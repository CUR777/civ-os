#!/usr/bin/env python3
"""
全量语义激发脚本
对输入文件的每个语义单元提取激发方向，
输出可供iterate.py处理的评论格式
"""
import sys
import requests
import json
from pathlib import Path
from datetime import datetime

MODEL = "pennyroyal"
API_URL = "http://127.0.0.1:8001/v1/chat/completions"
TIMEOUT = 300

SYSTEM_PROMPT = """你是文明OS的语义激发引擎。
对于输入的任何文本片段，遵循全量语义激发原则：
1. 识别每个语义单元（按语义完整性划分，不是按字数）
2. 对每个语义单元，找到它能激发的正向探索方向
3. 对负面/幼稚/碎片内容：提取其中隐含的需求、恐惧、期望或观察，转化为正向方向
4. 如果确实无法提取正向激发：输出「[待激发] + 原文」，不丢弃
5. 输出格式：每个激发结果用 > 💬 开头，一行一条

不要输出解释，直接输出激发结果。"""


def activate(text: str) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"对以下内容做全量语义激发：\n\n{text}"}
        ],
        "stream": False,
        "max_tokens": 4096,
        "temperature": 0.5
    }
    resp = requests.post(API_URL, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]



def activate_chunked(text: str, chunk_size: int = 3000) -> str:
    """对长文本分块激发，合并结果"""
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = []
    current_size = 0
    for para in paragraphs:
        para_size = len(para)
        if current_size + para_size > chunk_size and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    print(f" 分块模式：{len(chunks)}块（总{len(text)}字符）")
    results = []
    for i, chunk in enumerate(chunks):
        if len(chunk.strip()) < 50:
            continue
        print(f" 处理第{i+1}/{len(chunks)}块...", flush=True)
        result = activate(chunk)
        results.append(result)
    return '\n'.join(results)


def abstract_source_title(filename: str) -> str:
    """来源标题抽象化：去个人笔记风格特征（坑11规范）。只保留汉字/字母/数字/连字符，去日期噪声与尾部编号。"""
    name = re.sub(r'\.md$', '', filename)
    # 中文日期（2026年6月9日/2026年9月21日）整体删除
    name = re.sub(r'\d+年(\d+月)?(\d+日)?', ' ', name)
    # 删除非「汉字/字母/数字/连字符/下划线」以外的全部字符
    name = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9\-_]+', ' ', name)
    # 日期数字串：连字符式（2026-02-16）与空格分隔多段（08 11 48 184）
    name = re.sub(r'(?:\d{1,4}-){1,3}\d{1,4}', ' ', name)
    name = re.sub(r'(?:\b\d{1,4}[ ]){1,4}\d{1,4}\b', ' ', name)
    # 剩余独立数字串与尾部编号
    name = re.sub(r'\b\d{2,}\b', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip(' -_')
    name = re.sub(r'^AI\s*报告\s*[:：-]*\s*', '', name)
    return (name[:30].strip() or '知识库来源')


def main():
    if len(sys.argv) < 2:
        print("用法: python3 semantic_activate.py <输入文件> [目标节点文件]")
        print(" 输入文件: 要激发的文本文件（知识库笔记/日记/任何文本）")
        print(" 目标节点文件: 激发结果追加到哪个节点（可选，不指定则输出到屏幕）")
        sys.exit(1)

    src = Path(sys.argv[1])
    if not src.exists():
        print(f"文件不存在: {src}")
        sys.exit(1)

    content = src.read_text(encoding='utf-8', errors='ignore')
    print(f"输入文件: {src.name} ({len(content)}字符)")
    print("开始全量语义激发...")

    result = activate_chunked(content) if len(content) > 6000 else activate(content)

    if len(sys.argv) >= 3:
        # 追加到目标节点文件
        target = Path(sys.argv[2])
        if target.exists():
            current = target.read_text(encoding='utf-8')
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            addition = f"\n\n> 来源激发：[{abstract_source_title(src.name)}]（{ts}）\n\n{result}\n"
            target.write_text(current.rstrip('\n') + '\n' + addition, encoding='utf-8')
            print(f"已追加到: {target.name}")
        else:
            print(f"目标文件不存在: {target}")
            print("激发结果：")
            print(result)
    else:
        print("\n激发结果：")
        print(result)


if __name__ == "__main__":
    main()
