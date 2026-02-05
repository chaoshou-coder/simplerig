---
name: simplerig
description: SimpleRig Skill 驱动工作流。Agent 按阶段执行开发并记录事件。
---

# SimpleRig 工作流

当用户提出开发需求时，按以下流程执行（Agent 必须执行）。

## 交互优先级（避免卡住）

如果用户在执行流程中提出问题或插入讨论：

1. 先回答用户问题
2. 视情况记录暂停/恢复事件：
   ```bash
   simplerig emit run.paused --run-id <run_id> --data "{\"reason\":\"user_question\"}"
   # 回答问题
   simplerig emit run.resumed --run-id <run_id>
   ```
3. 回到原阶段继续执行

## 准备阶段

1. **检查安装**：
   ```bash
   python -m pip show simplerig
   ```
2. **检查配置**：确认项目根目录有 `config.yaml` 或 `SIMPLERIG_CONFIG`
3. **初始化 run**：
   ```bash
   # 优先使用
   simplerig init "用户的需求描述"
   # 如果上述命令失败，使用备用方式
   python -m simplerig.cli init "用户的需求描述"
   # 输出: run_id=20260205_120000_abc123
   ```
4. **记录 run_id**：后续命令都需要使用

## 阶段 1: 规划 (plan)

1. 分析用户需求并扫描项目结构
2. 制定开发计划，包含：
   - 需要创建的文件
   - 需要修改的文件
   - 实现步骤
3. 将计划保存到 `simplerig_data/runs/<run_id>/artifacts/plan.json`
4. 记录完成事件：
   ```bash
   simplerig emit stage.completed --stage plan --run-id <run_id>
   ```

## 阶段 2: 开发 (develop)

1. 读取 `plan.json`
2. 按计划创建/修改文件
3. 将变更记录到 `code_changes.json`
4. 记录完成事件：
   ```bash
   simplerig emit stage.completed --stage develop --run-id <run_id>
   ```

## 阶段 3: 验证 (verify)

1. 运行 Lint 检查：`ruff check .`
2. 运行测试：`pytest`
   - 若返回 exit code 5（未收集到测试），视为跳过，不视为失败
3. 将结果保存到 `verify_result.json`（无测试时标记为跳过）
4. 如果失败，回到阶段 2 修复
5. 记录完成事件：
   ```bash
   simplerig emit stage.completed --stage verify --run-id <run_id>
   ```

## 阶段 4: 完成

1. 汇总所有变更
2. 向用户报告完成情况
3. 记录完成事件：
   ```bash
   simplerig emit run.completed --run-id <run_id>
   ```

## 事件与产物

- 事件日志：`simplerig_data/runs/<run_id>/events.jsonl`
- 产物目录：`simplerig_data/runs/<run_id>/artifacts/`

## Token 统计（可选但推荐）

如果能从编辑器获得 Token，用事件记录真实使用量：

```bash
# 记录一次 LLM 调用
simplerig emit llm.called --run-id <run_id> --prompt-tokens 1200 --completion-tokens 340

# 或在阶段完成事件里附带
simplerig emit stage.completed --stage develop --run-id <run_id> --prompt-tokens 800 --completion-tokens 120
```

## 命令备用方式

如果 `simplerig` 命令不可用，使用 `python -m simplerig.cli` 替代：
```bash
python -m simplerig.cli init "需求"
python -m simplerig.cli emit stage.completed --stage plan --run-id <run_id>
python -m simplerig.cli status
```

## 断点续传

如果中断，用户说“继续”时：

1. `simplerig status` 查看最近运行状态
2. `simplerig tail --follow` 查看事件流
3. 从未完成阶段继续执行
