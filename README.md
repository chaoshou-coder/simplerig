# SimpleRig

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

多 Agent 工作流框架，同时支持 **Cursor** 和 **OpenCode**。

**核心改进：** 完全可配置，解决所有硬编码问题。

## 功能

- **需求挖掘** - Cursor Plan 模式，多轮提问 + 联网检索
- **智能规划** - 按**执行模型**的上下文要求拆分任务（关键改进）
- **并行开发** - 多 Agent 并行，验收选优
- **TDD 门控** - 红→绿测试驱动，3 次失败申请救兵
- **工作流监控** - 异常检测，自动停工
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

## 安装

```bash
pip install simplerig
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

```python
from simplerig import Planner, get_config

# 加载配置
config = get_config()

# 创建 Planner（自动按 dev 模型拆分任务）
planner = Planner(config)

tasks = planner.plan_from_architecture("""
# 系统架构
Module 1: 用户认证
Module 2: 数据存储
""")

for task in tasks:
    print(f"{task.id}: {task.assigned_model}, limit={task.estimated_context}")
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
