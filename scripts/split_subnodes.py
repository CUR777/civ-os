#!/usr/bin/env python3
"""
从顶层节点文件中提取模型生成的子节点内容，拆分为独立文件
用法：python3 scripts/split_subnodes.py 01 02 03 04
"""
import re, sys
from pathlib import Path

nodes_dir = Path('/home/v01/CUR-Agent/PROJECTS/civ-os/nodes')


def split_node(node_num):
    matches = list(nodes_dir.glob(f'节点{node_num}-*.md'))
    if not matches:
        print(f'节点{node_num}文件未找到')
        return
    src = matches[0]
    content = src.read_text(encoding='utf-8')
    sub_dir = nodes_dir / f'节点{node_num}'

    # 匹配子节点标题（### 子节点XX-XX：... 或 ## 子节点XX-XX：...）
    pattern = r'(#{2,3}\s*子节点[\d-]+[：:][^\n]*\n)([\s\S]*?)(?=#{2,3}\s*子节点|\Z)'
    matches_sub = re.findall(pattern, content)

    if not matches_sub:
        print(f'节点{node_num}：未找到子节点结构，需检查模型输出')
        return

    sub_dir.mkdir(exist_ok=True)
    for i, (title_line, body) in enumerate(matches_sub, 1):
        title_text = re.sub(r'^#{2,3}\s*', '', title_line).strip()
        name_part = re.sub(r'子节点[\d-]+[：:]', '', title_text).strip()
        name_clean = re.sub(r'[^\w\u4e00-\u9fff]', '-', name_part)[:30].strip('-')
        filename = f'子节点{node_num}-{str(i).zfill(2)}-{name_clean}.md'
        filepath = sub_dir / filename

        parent_glob = list(nodes_dir.glob(f'节点{node_num}-*.md'))
        parent_name = parent_glob[0].stem if parent_glob else f'节点{node_num}'

        header = f'## {title_text}\n\n'
        header += f'**所属节点**：[[nodes/{parent_name}|{parent_name}]]\n'
        header += '**层级**：第2层\n\n---\n\n'
        filepath.write_text(header + body.strip() + '\n', encoding='utf-8')
        print(f'  已创建: {filepath.name} ({len(body)}字符)')


for num in sys.argv[1:]:
    print(f'\n处理节点{num}...')
    split_node(num)
