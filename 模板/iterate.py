#!/usr/bin/env python3
"""
文明OS 迭代脚本 v0.3.0（多文件 + 超长文分块版）
扫描主页、主题页/与笔记库/（排除 iterations-/archive- 前缀快照）下所有含💬评论的文件→逐一调用模型整合→更新文件→git commit→push

v0.3.0 变更账（1011 云端提示词任务执行 · #ZZ-P300-1011-A · 2026-10-11 17:3x）：
  ① MAX_TOKENS 300000→320000（32万，37万压缩触发线下留5万缓冲；演变链 32768→400000→300000→320000）；
  ② TIMEOUT 900→1800（32万级单次整合最坏路径=长prefill+长生成，本地实测100~200 tok/s；与 sglang watchdog 1800 同档；服务端队列=无限等不拒绝，客户端超时不得抢跑）；
  ③ 超长文分块整合机制落地（A6-28/C7 注释条款→真实代码：全局摘要 map-reduce + 意群逐块整合，切点=段落边界，块目标~10万字）；
  ④ 结构性修复：P1-08 title_guard 插入事故致 main() 处理循环（候选收集之后的并发处理/守卫/提交段）被误嵌入 title_guard 的 return 之后成为死代码，本版恢复 main() 完整闭环；
  ⑤ 上下文填充原则注记（call_model 旁）。
"""

import requests, json, subprocess, sys, os, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

MODEL = "pennyroyal"
API_URL = "http://127.0.0.1:8001/v1/chat/completions"
HUB_FILE = "主题页/文明OS-主页.md"
SCAN_DIRS = ["主题页", "笔记库"]  # A35两层重构：一级主题+平铺笔记库均参扫
SNAPSHOT_PREFIXES = ("iterations-", "archive-")  # 历史快照冻结不参扫
PROMPT_FILE = "模板/system-prompt.md"
ITERATIONS_DIR = "笔记库"  # A35：迭代快照落笔记库，iterations- 前缀标识
TEMPERATURE = 0.3

#iterate.pyV20261011173100000+P300
# MAX_TOKENS 上限定为 320000（1011 云端提示词任务 · 改动原因按裁定原文记载）：
# 本地实测单窗口52万上下文稳定运行，但实测41万时曾卡住且未触发自动压缩机制，
# 龙虾智能体已设37万为压缩触发阈值。故上限定为32万，在37万压缩触发点之下留出5万缓冲。
# 原值32768在本地设备能力下是严重的保守性浪费。
# 上下文越长模型理解越完整，用保守性换细节损失不划算。
# 演变链（在册）：32768（早期默认保守值）→400000（A6-26决定，未生效）→300000（Phase9 现行值）→320000（本版）。
MAX_TOKENS = 320000

#iterate.pyV20261011173100000+T1800
# TIMEOUT 900→1800：32万上下文窗口下，单次整合调用的最坏路径 = 长 prefill + 长生成。
# 依据：①本地推理实测 100~200 tok/s，32万token级输入+万字级输出可越过900s；②sglang 官方文档长prompt走 chunked prefill（本机基线 chunked_prefill=4096），prefill 时长随输入线性增长；
# ③服务端排队语义=无限等待不拒绝请求，客户端超时属于本地侧保护，不应先于服务端完成而掐断（900s 会在排队+长生成场景制造假失败）；④与本机 sglang watchdog 1800s 同档对齐。
TIMEOUT = 1800

#iterate.pyV20261011173100000+CHUNK
# 超长文分块整合机制（A6-28 意群分块 + C7 切割自判 的落地代码；参数联动=上两条注记）：
# 当单个节点文件正文+评论总长度（估算token）超过 MAX_TOKENS×CHUNK_TRIGGER_RATIO 时：
#   ①按段落边界（意群近似，不切断任何行）把全文切成 ~CHUNK_TARGET_CHARS 字/块；
#   ②map-reduce 生成全局摘要（逐块局部摘要→汇总合并→终版全局摘要）；
#   ③带全局摘要+上块整合尾部上下文，逐块执行整合（每块输出=该块整合结果，禁虚构其它块内容）；
#   ④顺序拼接为完整文件后走原有 title_guard/validate/缩水守卫三道校验。
# 切点与整合粒度由模型自行掌握，机制层只做段落边界保底；不做人工评论密度控制，完全交给模型和设备能力。
CHUNK_TARGET_CHARS = 100000
CHUNK_TRIGGER_RATIO = 0.8

#iterate.pyV20261011151325000+A6-28
# 超长评论意群分块机制（1011 C1真缺补落 · 源=R0-链头0928 原文封存 L509/L565，登记号 R0#A6-28）：
# 评论超过单窗口上限（如百万字级连续一段）时，由模型自行按意群截断分块（参考量级：每块~10万字）
# → 先生成全局摘要 → 带着摘要逐块处理；具体分块位置/方式由模型自行判断，不做人工预设。
# MAX_TOKENS 现值旁注：原决定值=400000（A6-26），本文件现行生效值=300000；两者差异以代码实值为准，引用前先看本行。
# （1011 17:3x 勘注：本行「现行生效值=300000」已被 V20261011173100000+P300 升为 320000，以 P300 行及代码实值为准。）

#iterate.pyV20261011155205000+B23
# 40万级参数观察期策略（1011 C1重判真缺候选兑现 · 源=R0-链头0928 原文封存L1209＋R3-0929c L374 双源同文，台账编号 R0#回3B23/R1#B23）：
# MAX_TOKENS 等参数升档决定落地时不设特殊观察期 → 常态运行，出问题再微调（收益>>损失）；本行=该策略在参数类决定上的常载点。

#iterate.pyV20261011151325000+C7
# 意群切割自判配套（1011 C1真缺补落 · 源=R0-链头0928 原文封存 L596，登记号 R0#回3C7）：
# 超长分块（如100万字按意群分~10块）的切割质量取决于模型对内容的理解 → 切割位置由模型自行判断，人不干预；
# 效果不好时在后续迭代中调整，不回退为人工切割。


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
    #iterate.pyV20261011173100000+FILL
    # 上下文填充原则（1011 云端提示词任务 2.4）：
    # ①不用无关内容填满窗口；②但凡有潜在相关/可能相关的信息就拉进上下文；
    # ③上下文溢出时由主线智能体自然报错反馈，届时再微调，不预设保守限制（同 B23 无观察期策略）。
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


def estimate_tokens(text):
    # token估算：中英混合文按 0.5 token/字节 保守折算（CJK≈1tok/3B，ASCII≈1tok/4B），宁高勿低=提前进分块轨道
    return int(len(text.encode('utf-8')) * 0.5)


def paragraph_chunks(content, target_chars):
    """按段落边界（\n\n）贪心打包 ~target_chars 字/块；超长单段独立成块（意群保底不切断）。
    返回 [(块文本, 连接分隔符), ...]，分隔符用于无损拼接。"""
    paras = content.split('\n\n')
    chunks = []
    buf, buf_len = [], 0
    for para in paras:
        plen = len(para)
        if buf and buf_len + plen > target_chars:
            chunks.append('\n\n'.join(buf))
            buf, buf_len = [para], plen
        else:
            buf.append(para)
            buf_len += plen
        if plen > target_chars and len(buf) == 1:
            chunks.append(para)
            buf, buf_len = [], 0
    if buf:
        chunks.append('\n\n'.join(buf))
    return [(c, '\n\n') for c in chunks]


def rolling_global_summary(chunks):
    """map-reduce 全局摘要：逐块局部摘要→合并→终版。分块整合的②步。"""
    part_summaries = []
    for i, (chunk, _) in enumerate(chunks, 1):
        s = call_model(
            "你是文明OS迭代引擎的摘要工序。对给定文段输出≤300字中文摘要：保留章节/标题结构、编号族（A/B/C/D/E/N/H/K/I/TDB等）关键条目、数值+单位、裁定与状态、待办。只输出摘要本身。",
            f"【全文共{len(chunks)}块，当前第{i}块】\n\n{chunk}")
        part_summaries.append(f"块{i}摘要：{s.strip()}")
    merged = '\n'.join(part_summaries)
    if len(part_summaries) == 1:
        return merged
    final = call_model(
        "你是文明OS迭代引擎的摘要工序。把下列分段摘要合并为一份≤1500字的全局摘要：保留全部编号族要点、数值+单位、裁定与状态、跨块关联线索，去重不虚构。只输出摘要本身。",
        merged)
    return final.strip()


def integrate_chunked(system_prompt, content, fname):
    """超长文件整合：②全局摘要 ③带摘要逐块整合 ④拼接返回完整新文本。"""
    chunks = paragraph_chunks(content, CHUNK_TARGET_CHARS)
    if len(chunks) <= 1:
        return call_model(system_prompt, content)
    print(f"   ✂ 分块整合：{fname} 共{len(chunks)}块（目标~{CHUNK_TARGET_CHARS}字/块）")
    gsum = rolling_global_summary(chunks)
    outs, prev_tail = [], ''
    for i, (chunk, sep) in enumerate(chunks, 1):
        ctx = f"【全局摘要】\n{gsum}\n\n"
        if prev_tail:
            ctx += f"【上一块整合结果尾部（供衔接，勿重复输出）】\n{prev_tail}\n\n"
        body = call_model(
            system_prompt,
            ctx + f"【当前块：全文{len(chunks)}块中的第{i}块，正文如下。仅输出本块整合更新后的完整文本，禁止虚构或改写未在本块出现的任何内容；清除本块内已整合的评论行/已读标记；保持本块原有结构、编号、数值原样保真】\n\n{chunk}")
        body = body.rstrip() + sep
        outs.append(body)
        prev_tail = body[-800:] if len(body) > 800 else body
    return ''.join(outs)


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


def title_guard(orig: str, new: str, fname: str) -> bool:
    """P1-08 防串写校验：首行标题必须与目标文件一致，否则中止写入（节点16串写案根治）。"""
    ol=[l for l in orig.strip().splitlines() if l.strip()]
    nl=[l for l in new.strip().splitlines() if l.strip()]
    if not ol: return True
    of=ol[0].strip(); nf=(nl[0] if nl else '')
    if of.startswith('#'):
        core=of.lstrip('#').strip()
        # 文件名推导的核心题（去 front-matter 风格差异）：要求新首行仍含原标题主体
        base=core.split('（')[0].split('(')[0][:18]
        if base and base not in nf:
            return False
    if '系统提示词' in nf and '系统提示词' not in fname and 'system' not in fname.lower():
        return False  # 串写黑名单：提示词标题出现在非提示词文件
    return True


def process_file(fpath, system_prompt):
    """单文件完整处理流程；返回 (更新路径|None, 日志行)。写回各自文件，线程安全。"""
    content = read_file(str(fpath))
    if not has_comments(content):
        return None, f"  跳过（无评论）: {fpath.name}"
    ts_inner = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = Path(ITERATIONS_DIR) / f"iterations-{fpath.stem}_{ts_inner}.md"
    write_file(str(backup), content)
    try:
        #iterate.pyV20261011173100000+CHUNK调用
        if estimate_tokens(content) > MAX_TOKENS * CHUNK_TRIGGER_RATIO:
            new_content = integrate_chunked(system_prompt, content, fpath.name)
        else:
            new_content = call_model(system_prompt, content)
    except Exception as e:
        return None, f" ❌ 模型调用失败: {fpath.name}: {e}"
    if not title_guard(content, new_content, fpath.name):
        err_path = Path(ITERATIONS_DIR) / f"iterations-crosswrite_{fpath.stem}_{ts_inner}.md"
        write_file(str(err_path), new_content)
        print(f" 🛑 防串写校验中止整批: {fpath.name} 首行与文件不符")
        raise SystemExit(2)
    if not validate(new_content, str(fpath)):
        err_path = Path(ITERATIONS_DIR) / f"iterations-failed_{fpath.stem}_{ts_inner}.md"
        write_file(str(err_path), new_content)
        return None, f" ⚠️ 校验失败，原文件保持不变: {fpath.name}"
    if len(new_content.encode('utf-8')) < len(content.encode('utf-8')) * 0.5:
        err_path = Path(ITERATIONS_DIR) / f"iterations-failed_{fpath.stem}_{ts_inner}.md"
        write_file(str(err_path), new_content)
        return None, f" ⚠️ 体积缩水超半，原文件保持不变: {fpath.name}"
    write_file(str(fpath), format_fix(new_content))
    return str(fpath), f" ✅ 处理完成: {fpath.name}"


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n{'='*60}")
    print(f"文明OS 迭代开始 — {ts}")
    print(f"{'='*60}\n")

    system_prompt = read_file(PROMPT_FILE)
    core_snapshot = get_immutable_core()  # 不可变核心区快照（防迭代旁路污染）

    # 并行模式（默认4并行：sglang max-running-requests=16 实测4路真并行无排队，功耗与2路相同；--parallel N 可覆盖，0/1=串行）
    #iterate.pyV20261011173100000+PRL4注
    # 32万上下文下的并行评估（1011 联动参数检查）：保持默认4——本机实测 max-running-requests=16、4路无排队；
    # KV缓存压力按 sglang 文档由服务端 chunked prefill + hicache 分级消化，排队而非冲突拒绝；若多文件同时触发分块整合（每块10万字级×多路），
    # 建议显式 `--parallel 2` 降载。默认值不动=以实测为准，微调走 B23 常态运行通道。
    parallel = 4
    if '--parallel' in sys.argv:
        try:
            parallel = max(1, int(sys.argv[sys.argv.index('--parallel') + 1]))
        except (IndexError, ValueError):
            parallel = 3
        print(f" 并行模式：{parallel} 个工作线程")

    # 收集所有需要处理的文件（主页+主题页/+笔记库/，快照前缀除外）
    candidates = [Path(HUB_FILE)]
    for d in SCAN_DIRS:
        dp = Path(d)
        if dp.exists():
            candidates += sorted(p for p in dp.rglob("*.md")
                                 if not p.name.startswith(SNAPSHOT_PREFIXES))

    print(f"[扫描] 共{len(candidates)}个文件")

    changed_files = []
    def _fp(f):
        return process_file(f, system_prompt)

    if parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {executor.submit(_fp, f): f for f in candidates}
            for future in as_completed(futures):
                path, msg = future.result()
                print(msg, flush=True)
                if path:
                    changed_files.append(path)
    else:
        for fpath in candidates:
            path, msg = _fp(fpath)
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
