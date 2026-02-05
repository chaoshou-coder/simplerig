---
name: simplerig
description: SimpleRig Skill 驱动工作流。Agent 按阶段执行开发并记录事件。
---

# SimpleRig 工作流

当用户提出开发需求时，按以下流程执行（Agent 必须执行）。

## 准备阶段

1. **检查安装**：
   ```bash
   python -m pip show simplerig
   ```
2. **检查配置**：确认项目根目录有 `config.yaml` 或 `SIMPLERIG_CONFIG`
3. **初始化 run**：
   ```bash
   simplerig init "用户的需求描述"
   # 输出: run_id=20260205_120000_abc123
   ```
4. **记录 run_id**：后续命令都需要使用

## 阶段 1: 规划 (plan)

1. 分析用户需求并扫描项目结构
2. 制定开发计划，包含：
   - 需要创建的文件
   - 需要修改的文件
   - 实现步骤
3. 将计划保存到 `.simplerig/runs/<run_id>/artifacts/plan.json`
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
3. 将结果保存到 `verify_result.json`
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

- 事件日志：`.simplerig/runs/<run_id>/events.jsonl`
- 产物目录：`.simplerig/runs/<run_id>/artifacts/`

## 断点续传

如果中断，用户说“继续”时：

1. `simplerig status` 查看最近运行状态
2. `simplerig tail --follow` 查看事件流
3. 从未完成阶段继续执行
