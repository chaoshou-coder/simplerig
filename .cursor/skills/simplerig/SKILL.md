---
name: simplerig
description: "SimpleRig 多阶段开发工作流：规划→开发→验证→完成，并记录事件。在以下情况必须启用本 Skill：用户提到「开发计划」「执行计划」「按计划执行」「现在执行」、或 @ 引用 .cursor/plans/*.plan.md、或要求按既有计划/需求执行开发时。也可通过 /simplerig 显式调用。"
---

# SimpleRig 工作流

**何时启用本 Skill**：用户 @ 了 `.cursor/plans/*.plan.md`、或说「开发计划现在执行」「按计划执行」、或提出开发需求/要按既有计划执行时，都应启用本 Skill（无需用户必须输入 /simplerig）。

当用户提出开发需求或要求执行计划时，按以下流程执行（Agent 必须执行）。

## Shell 与平台（必读，避免无效重试）

- **Windows PowerShell 不支持 `&&`**：不要使用 `cd 路径 && 命令`。应使用分号写在同一行，或先 `cd` 再在下一步执行命令。
  - 正确：`cd e:\code\PROJECT; python -m pip show simplerig`
  - 错误：`cd /d e:\code\PROJECT && python -m pip show simplerig`
- **`simplerig init` 的参数字符串**：在 PowerShell 下，双引号内过长或含中文时易报错「缺少终止符」。**优先用简短英文描述**（如 `"OpenClaw context manager - CLI and API"`），详细需求写在后续 plan 或 @ 的文档里即可。
- **命令入口**：若 `simplerig` 未找到，一律用 `python -m simplerig.cli`。若仍报 `No module named simplerig.cli`，说明当前环境安装的是别的包或旧结构，需在当前项目下执行 `pip install -e <本机 SimpleRig 仓库路径>` 再重试。

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

1. **进入项目根目录**（若需切换）：用 `cd 路径`；在 PowerShell 中与下一命令用 `;` 分隔，不要用 `&&`。
2. **检查安装**（任选一种，在项目根下执行）：
   ```bash
   python -m pip show simplerig
   ```
   若无 `simplerig` 或版本/路径不对，在当前项目虚拟环境中安装：`pip install -e <SimpleRig 仓库路径>`。
3. **检查配置**：确认项目根目录有 `config.yaml` 或环境变量 `SIMPLERIG_CONFIG`。
4. **初始化 run**（在项目根下执行）：
   - 使用**简短英文描述**以避免 PowerShell 引号/编码问题，例如：`"OpenClaw context manager - CLI ocm, HTTP API, skills"`。详细需求由规划阶段从 @ 的 plan 或文档中读取。
   ```bash
   simplerig init "Short English description here"
   ```
   若 `simplerig` 命令不存在，改用：
   ```bash
   python -m simplerig.cli init "Short English description here"
   ```
   从输出中取得 `run_id=...`，后续所有 emit 均需带上 `--run-id <run_id>`。

## 阶段 1: 规划 (plan)

1. 记录开始事件：
   ```bash
   simplerig emit stage.started --stage plan --run-id <run_id>
   ```
2. 分析用户需求并扫描项目结构
3. 制定开发计划，包含：
   - 需要创建的文件
   - 需要修改的文件
   - 实现步骤
4. 将计划保存到 `simplerig_data/runs/<run_id>/artifacts/plan.json`
5. 记录完成事件：
   ```bash
   simplerig emit stage.completed --stage plan --run-id <run_id>
   ```

## 阶段 2: 开发 (develop)

1. 记录开始事件：
   ```bash
   simplerig emit stage.started --stage develop --run-id <run_id>
   ```
2. 读取 `plan.json`
3. 按计划创建/修改文件
4. 将变更记录到 `code_changes.json`
5. 记录完成事件：
   ```bash
   simplerig emit stage.completed --stage develop --run-id <run_id>
   ```

## 阶段 3: 验证 (verify)

1. 记录开始事件：
   ```bash
   simplerig emit stage.started --stage verify --run-id <run_id>
   ```
2. 运行 Lint 检查：`ruff check .`
3. 运行测试：`pytest`
   - 若返回 exit code 5（未收集到测试），视为跳过，不视为失败
4. 将结果保存到 `verify_result.json`（无测试时标记为跳过）
5. 如果失败，回到阶段 2 修复
6. 记录完成事件：
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

## TDD / BDD 模式（可选）

- **TDD 模式**（`--tdd`）：在 `simplerig run` 时启用。develop 阶段会执行红绿循环：若 `plan.json` 中提供 `tdd_test_file` / `tdd_impl_file`，将调用 `TDDRunner.run_cycle()`，并通过事件发射 `tdd.red_started`、`tdd.green_passed`、`tdd.cycle_completed` 等。
- **BDD 模式**（`--bdd`）：在 `simplerig run` 时启用。verify 阶段会扫描 `artifacts/` 下的 `.feature` 文件并用 `BDDRunner` 执行，结果写入 `verify_result.json` 的 `bdd` 字段，并生成 `bdd_report.json` / `bdd_report.html`。
- **独立 BDD 命令**：
  - `simplerig bdd generate <spec.json>`：从规格 JSON 生成 `.feature` 文件
  - `simplerig bdd run <path.feature>`：单独运行 BDD 测试，支持 `--report text|json|html`

示例：
```bash
simplerig run "需求" --tdd
simplerig run "需求" --bdd
simplerig bdd generate spec.json -o features/
simplerig bdd run features/demo.feature --report html
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

若终端中 `simplerig` 不可用，一律使用 `python -m simplerig.cli`（同上，init 参数用简短英文）：
```bash
python -m simplerig.cli init "Short description"
python -m simplerig.cli emit stage.completed --stage plan --run-id <run_id>
python -m simplerig.cli status
```
若报 `No module named simplerig.cli`，说明当前环境未正确安装本仓库的 SimpleRig，需在项目下执行 `pip install -e <SimpleRig 仓库路径>` 后再试。

## 断点续传

如果中断，用户说“继续”时：

1. `simplerig status` 查看最近运行状态
2. `simplerig tail --follow` 查看事件流
3. 从未完成阶段继续执行
