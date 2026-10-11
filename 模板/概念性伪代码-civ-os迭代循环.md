# 概念性伪代码 — civ-os 迭代循环（T10-3 回写 · 环10 K7X · 10-11 P3-04）

#概念性伪代码 — civ-os 迭代循环（T10-3 回写 · 环10 K7X · 10-11 P3-04）V20261011024806000+A1

> 性质=**概念性伪代码**（十轮收敛的原理级蓝图，非运行代码）；实际最小实现=iterate.py（本目录）。二者关系：本文件=架构意图层，iterate.py=当前工程执行层，迭代只增强不替换（K7 原则）。

```python
# civ-os 核心迭代循环（while True 八步 · 环10 定稿原文结构）
while True:
    # ① 收集输入：讨论/分析/外部数据
    new_insights = gather_from_all_sources()
    # ② 整合到框架
    framework.integrate(new_insights)
    # ③ 检查公理一致性；如有违反则修正偏离公理的部分
    violations = axiom_check(framework)
    if violations:
        framework.resolve(violations)
    # ④ 更新安全体系
    safety_system.update(framework.changes)
    # ⑤ 生成改进建议
    improvements = framework.propose_improvements()
    # ⑥ 验证改进：通过逻辑验证→应用；未通过→归档留因
    for imp in improvements:
        if imp.passes_logic_verification():
            framework.apply(imp)
        else:
            framework.archive(imp, reason="未通过逻辑验证")
    # ⑦ 输出更新：更新所有 markdown 文件
    framework.export()
    # ⑧ 等待下一轮输入（迭代间隔视场景而定：单会话轮次=秒级；版本迭代周期=日/月级；文明演化迭代=年/代际级）
    sleep(iteration_interval)
```

**读解注**：步骤③=公理Ⅰ~Ⅲ为硬校验器（自编辑面全可改、公理不可改在此步体现）；步骤⑥=「自由迭代就要提供证据」的机械形态（未过验证不丢弃、归档留因，对应评论只追加不删除）；步骤⑧=9~30 秒/轮为概念量级，工程现实=按评论到达节奏触发。
