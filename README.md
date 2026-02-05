# SimpleRig

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

多 Agent 工作流框架，同时支持 **Cursor** 和 **OpenCode**。

**核心改进：** 完全可配置，JSONL 事件溯源，任务级并行，断点续传。

## 功能

- **CLI 命令行** - `simplerig run/status/tail/list/stats` 完整命令行支持
- **JSONL 事件溯源** - 所有操作记录为 `events.jsonl`，可审计、可重放
- **任务级并行** - DAG 依赖调度，并发上限控制，失败隔离
- **断点续传** - `--resume` 从中断处继续，`--from-stage` 指定阶段开始
- **产物落盘** - 所有中间结果存储到 `artifacts/`，SHA256 校验
- **统计报告** - 总耗时、Token 消耗、各阶段/任务详细统计
- **智能规划** - 按**执行模型**的上下文要求拆分任务
- **Lint 门禁** - 可配置的代码风格检查（支持 ruff/flake8/pylint）

## 关键改进

### 1. 完全可配置

所有硬编码改为从 `config.yaml` 读取：

```yaml
# 模型配置 - 不再硬编码
models:
  registry:
    opencode/kimi-k2.5-free:
      context_limit: 8000
      performance_degradation_point: 0.70
    # 可添加任意模型
    
  roles:
    architect: "openai/gpt-5.2-codex"
    planner: "openai/gpt-5.2-codex"
    dev: "opencode/kimi-k2.5-free"  # 按此模型拆分任务

# 工具链配置 - 不再硬编码 ruff/black/pytest
tools:
  linter: "ruff"  # 或 "flake8", "pylint"
  formatter: "black"  # 或 "autopep8"
  test_runner: "pytest"  # 或 "unittest"

# 超时配置 - 可配置
timeouts:
  tdd_max_retries: 3
  monitor_stall: 60
  
# 项目结构 - 可配置
project:
  source_dirs: ["src", "lib"]
  test_dirs: ["tests", "test"]
```

### 2. 按执行模型拆分任务

**旧问题**：Planner 按规划模型拆分，执行模型换后可能不匹配。

**解决**：
```python
# 获取执行模型（dev）的上下文要求
dev_model_name, dev_config = config.get_model("dev")
safe_limit = dev_config.safe_limit

# 按执行模型的限制拆分任务
tasks = planner.plan_from_architecture(arch)
# 每个任务都确保在 dev 模型的安全限制内
```

### 3. 路径可配置

```yaml
paths:
  database: "${SIMPLERIG_DB:-./.simplerig/memory.db}"
  logs: "${SIMPLERIG_LOGS:-./.simplerig/logs}"
  temp: "${SIMPLERIG_TEMP:-./.simplerig/temp}"
```

支持环境变量，不再硬编码 `./.workflow`。

## 前置要求

- **Python 3.10+**
- 使用 Cursor/OpenCode 集成时需已安装对应 IDE

## 安装

### 从 PyPI 安装（推荐）

```bash
pip install simplerig
```

### 从源码安装（开发者 / 从 GitHub clone 后）

若你从 GitHub clone 了本仓库，在项目根目录执行：

```bash
# 创建并激活虚拟环境
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

# 可编辑安装（含开发依赖：pytest、pytest-bdd、black、ruff）
pip install -e ".[dev]"

# 验证
simplerig --help
pytest -q  # 运行测试
```

安装后可直接使用 `simplerig` 命令；修改源码会立即生效（无需重装）。

## CLI 使用

```bash
# 运行工作流
simplerig run "实现用户认证功能"

# 预演模式（不实际执行）
simplerig run "实现功能" --dry-run

# 断点续传（从最近一次中断处继续）
simplerig run --resume

# 从指定 run 恢复
simplerig run --resume abc123

# 从指定阶段开始
simplerig run "实现功能" --from-stage develop

# 查看运行状态
simplerig status --run-id abc123

# 查看事件流
simplerig tail --run-id abc123 --follow

# 列出历史运行
simplerig list --limit 10

# 查看统计报告
simplerig stats                  # 最近一次运行
simplerig stats --run-id abc123  # 指定运行
simplerig stats --json           # JSON 格式输出
```

### Run 目录结构

```
.simplerig/runs/<run_id>/
├── events.jsonl      # 事件流（事实源）
├── artifacts/        # 产物目录
│   ├── plan.json
│   ├── code_changes.json
│   ├── verify_result.json
│   └── stats.json    # 统计报告
└── locks/
    └── run.lock      # 互斥锁
```

## Cursor 集成

### Agent Skills

```bash
cp -r .cursor/skills/simplerig /your/project/.cursor/skills/
```

在 Cursor 中输入 `/simplerig` 或描述开发需求。

## OpenCode 集成

```bash
cp -r .opencode/skills/simplerig /your/project/.opencode/skills/
```

## 快速开始

### 使用 CLI

已通过 PyPI 或源码安装后，在**你的项目目录**下：

```bash
# 可选：复制默认配置到当前项目（若需自定义）
cp /path/to/SimpleRig/config.yaml ./config.yaml

# 运行一次工作流
simplerig run "实现用户登录功能"
```

若尚未安装，请先完成上方 [安装](#安装) 步骤。

### 使用 Python API

```python
from simplerig import (
    run_workflow,
    run_parallel_tasks,
    Task,
    get_config,
)
from pathlib import Path

# 运行阶段工作流
run_dir = Path(".simplerig/runs/my_run")
run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "locks").mkdir(exist_ok=True)

state = run_workflow(run_dir, requirement="实现用户认证")
print(f"状态: {state.status}")
print(f"完成阶段: {state.completed_stages}")
```

### 并行任务调度

```python
from simplerig import Task, run_parallel_tasks
from pathlib import Path

run_dir = Path(".simplerig/runs/parallel_run")
run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "locks").mkdir(exist_ok=True)

# 定义任务（无依赖 = 可并行）
tasks = [
    Task(id="t1", name="处理模块A"),
    Task(id="t2", name="处理模块B"),
    Task(id="t3", name="处理模块C"),
    Task(id="t4", name="合并结果", dependencies=["t1", "t2", "t3"]),
]

# 并行执行
results = run_parallel_tasks(run_dir, tasks, max_workers=3)

for task_id, result in results.items():
    print(f"{task_id}: {result.status.value}")
```

### 事件系统

```python
from simplerig import EventWriter, EventReader, ArtifactStore
from pathlib import Path

run_dir = Path(".simplerig/runs/event_demo")
run_dir.mkdir(parents=True, exist_ok=True)

# 写入事件
writer = EventWriter(run_dir)
writer.emit("run.started", "demo", requirement="测试")
writer.emit("task.completed", "demo", task_id="t1")

# 写入产物
store = ArtifactStore(run_dir)
ref = store.write("output.json", {"result": "success"})
writer.emit("artifact.written", "demo", artifact=ref.to_dict())

# 读取事件
reader = EventReader(run_dir)
for event in reader.iter_events():
    print(f"[{event.seq}] {event.type}: {event.data}")
```

### 统计功能

```python
from simplerig import collect_stats, format_duration
from pathlib import Path

run_dir = Path(".simplerig/runs/my_run")

# 收集统计
stats = collect_stats(run_dir)

# 输出摘要
print(stats.summary())

# 访问详细数据
print(f"总耗时: {format_duration(stats.total_duration_ms)}")
print(f"总 Token: {stats.total_token_usage.total_tokens:,}")

# 各阶段统计
for name, stage in stats.stages.items():
    print(f"{name}: {stage.status}, {format_duration(stage.duration_ms)}")

# 导出 JSON
import json
print(json.dumps(stats.to_dict(), indent=2, ensure_ascii=False))
```

## 配置详解

### 模型配置

```yaml
models:
  registry:
    # 任意模型，不再限于3个
    your-model-name:
      context_limit: 16000
      performance_degradation_point: 0.75  # 75% 开始下降
      optimal_context: 8000
      cost_per_1k: 0.001
      strengths: ["code_gen", "analysis"]
```

### 工具链配置

```yaml
tools:
  linter: "flake8"
  linter_args: ["--max-line-length=120"]
  
  formatter: "autopep8"
  formatter_args: ["--in-place", "--aggressive"]
  
  test_runner: "unittest"
  test_runner_args: ["discover", "-v"]
```

### 完整配置示例

见 [config.yaml](./config.yaml)

## 文档

- **功能规格**： [docs/features/stats-spec.md](./docs/features/stats-spec.md)（统计功能技术规格）
- **BDD 场景**： [docs/features/stats.feature](./docs/features/stats.feature)
- **配置说明**：见本 README「配置详解」及仓库内 [config.yaml](./config.yaml)

## 与 cursor-opencode-workflow 的区别

| 问题 | cursor-opencode-workflow | SimpleRig |
|------|-------------------------|-----------|
| 模型配置 | 硬编码3个模型 | 任意模型，config 配置 |
| 任务拆分 | 按规划模型拆分 | 按**执行模型**拆分 |
| 工具链 | 硬编码 ruff/black/pytest | 可配置 |
| 路径 | 硬编码 `./.workflow` | 环境变量 + 配置 |
| 超时 | 硬编码 | 可配置 |

## 许可

[MIT License](./LICENSE)
