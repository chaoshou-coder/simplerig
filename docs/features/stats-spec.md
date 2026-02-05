# 统计功能技术规格

> 版本: 1.0.0  
> 日期: 2026-02-05  
> 状态: 已实现

## 概述

统计功能提供工作流执行的详细统计信息，包括总耗时、Token 消耗、各阶段/任务的详细指标。基于 Event Sourcing 架构，从 `events.jsonl` 收集统计数据。

## 功能清单

### 1. 自动统计显示

**触发条件**: 工作流执行完成后（无论成功或失败）

**输出示例**:
```
============================================================
Run 统计: 20260205_120000_abc123
============================================================
状态: completed
需求: 实现用户认证功能

【总体统计】
  总耗时: 5m 23.4s
  总 Token: 15,234
    - 输入: 12,456
    - 输出: 2,778

【阶段统计】
  阶段           状态         耗时                   Token
  --------------------------------------------------
  plan         completed  12.34s                 1,234
  develop      completed  4m 5.6s                8,765
  verify       completed  45.67s                 3,456
  integrate    completed  8.12s                  1,779

============================================================
```

### 2. stats 子命令

**命令格式**:
```bash
simplerig stats [--run-id RUN_ID] [--json]
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--run-id` | string | 否 | 指定运行 ID，默认为最近一次运行 |
| `--json` | flag | 否 | 以 JSON 格式输出 |

**退出码**:

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 运行不存在或无运行记录 |

### 3. 统计数据持久化

**存储位置**: `.simplerig/runs/<run_id>/artifacts/stats.json`

**触发时机**: `run.completed` 或 `run.failed` 事件发生时

## 数据结构

### TokenUsage

Token 使用量统计。

```python
@dataclass
class TokenUsage:
    prompt_tokens: int = 0      # 输入 tokens
    completion_tokens: int = 0  # 输出 tokens
    total_tokens: int = 0       # 总 tokens
```

**方法**:
- `__add__(other: TokenUsage) -> TokenUsage`: 支持加法运算
- `to_dict() -> Dict[str, int]`: 转换为字典
- `from_dict(data: Dict) -> TokenUsage`: 从字典创建（类方法）

### StageStats

阶段统计。

```python
@dataclass
class StageStats:
    name: str                              # 阶段名称
    status: str = "unknown"                # 状态: pending/running/completed/failed/skipped
    duration_ms: int = 0                   # 耗时（毫秒）
    token_usage: TokenUsage = field(...)   # Token 使用量
    start_time: Optional[str] = None       # 开始时间（ISO 8601）
    end_time: Optional[str] = None         # 结束时间（ISO 8601）
```

### TaskStats

任务统计。

```python
@dataclass
class TaskStats:
    task_id: str                           # 任务 ID
    name: str = ""                         # 任务名称
    status: str = "unknown"                # 状态
    duration_ms: int = 0                   # 耗时（毫秒）
    token_usage: TokenUsage = field(...)   # Token 使用量
```

### RunStats

运行统计（顶层聚合）。

```python
@dataclass
class RunStats:
    run_id: str                                    # 运行 ID
    status: str = "unknown"                        # 状态
    requirement: str = ""                          # 需求描述
    
    start_time: Optional[str] = None               # 开始时间
    end_time: Optional[str] = None                 # 结束时间
    total_duration_ms: int = 0                     # 总耗时
    
    total_token_usage: TokenUsage = field(...)     # 总 Token 消耗
    
    stages: Dict[str, StageStats] = field(...)     # 阶段统计
    tasks: Dict[str, TaskStats] = field(...)       # 任务统计
    
    event_count: int = 0                           # 事件数
```

**方法**:
- `to_dict() -> Dict`: 转换为字典（可 JSON 序列化）
- `summary() -> str`: 生成可读摘要文本

## API 接口

### collect_stats(run_dir: Path) -> RunStats

从运行目录收集统计信息。

**参数**:
- `run_dir`: 运行目录路径（包含 `events.jsonl`）

**返回**: `RunStats` 对象

**示例**:
```python
from simplerig import collect_stats
from pathlib import Path

stats = collect_stats(Path(".simplerig/runs/20260205_120000_abc123"))
print(stats.summary())
```

### save_stats(run_dir: Path, stats: RunStats)

保存统计到 artifacts。

**参数**:
- `run_dir`: 运行目录路径
- `stats`: 统计对象

**效果**: 在 `artifacts/stats.json` 创建或覆盖统计文件

### format_duration(ms: int) -> str

格式化耗时为人类可读格式。

**参数**:
- `ms`: 毫秒数

**返回**: 格式化字符串

**格式规则**:

| 范围 | 格式 | 示例 |
|------|------|------|
| < 1秒 | `{ms}ms` | `500ms` |
| 1秒 ~ 1分钟 | `{s:.2f}s` | `45.67s` |
| 1分钟 ~ 1小时 | `{m}m {s:.1f}s` | `5m 23.4s` |
| ≥ 1小时 | `{h}h {m}m` | `2h 15m` |

## 事件处理

### 监听的事件类型

| 事件类型 | 处理逻辑 |
|----------|----------|
| `run.started` | 设置 status="running", 记录 start_time, 提取 requirement |
| `run.completed` | 设置 status="completed", 记录 end_time |
| `run.failed` | 设置 status="failed", 记录 end_time |
| `stage.started` | 创建/更新阶段, 设置 status="running", 记录 start_time |
| `stage.completed` | 更新阶段 status="completed", 记录 duration_ms 和 token_usage |
| `stage.failed` | 更新阶段 status="failed", 记录 duration_ms |
| `stage.skipped` | 设置阶段 status="skipped" |
| `task.created` | 创建任务记录, status="pending" |
| `task.started` | 更新任务 status="running", 记录 start_time |
| `task.completed` | 更新任务 status="completed", 记录 duration_ms 和 token_usage |
| `task.failed` | 更新任务 status="failed" |
| `llm.called` | 累加 token_usage 到总量 |

### Token 累加规则

1. **阶段级别**: `stage.completed` 事件中的 `token_usage` 累加到总量
2. **任务级别**: `task.completed` 事件中的 `token_usage` 累加到总量
3. **LLM 调用**: `llm.called` 事件中的 `token_usage` 累加到总量

> **注意**: 阶段和任务的 token_usage 是独立统计的，不存在包含关系。

## 敏感数据处理

### 安全字段（不脱敏）

```python
SAFE_KEYS = {
    'token_usage',
    'prompt_tokens', 
    'completion_tokens',
    'total_tokens',
}
```

### 敏感字段（需脱敏）

```python
SENSITIVE_KEYS = {
    'password',
    'secret',
    'api_key',
    'apikey',
    'token',        # 注意: token_usage 等安全字段不受此影响
    'credential',
    'auth',
    'secret_token',
    # ...
}
```

## 测试覆盖

### 单元测试 (tests/test_stats.py)

| 测试类 | 测试内容 |
|--------|----------|
| `TestTokenUsage` | TokenUsage 加法、序列化、反序列化 |
| `TestFormatDuration` | 各时间范围的格式化 |
| `TestStatsCollector` | run/stage/task 事件处理、token 累加 |
| `TestRunStats` | summary 生成、to_dict 转换 |
| `TestSaveStats` | artifacts 保存 |
| `TestIntegration` | 完整工作流统计 |

### 测试命令

```bash
# 运行统计模块测试
pytest tests/test_stats.py -v

# 运行所有测试
pytest tests/ -v
```

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `simplerig/stats.py` | 新增 | 统计模块核心实现 |
| `simplerig/runner.py` | 修改 | 集成统计收集和保存 |
| `simplerig/cli.py` | 修改 | 添加 stats 子命令, run 后显示统计 |
| `simplerig/events.py` | 修改 | 修复敏感数据脱敏逻辑 |
| `simplerig/__init__.py` | 修改 | 导出统计相关 API |
| `tests/test_stats.py` | 新增 | 统计模块测试 |
| `README.md` | 修改 | 添加统计功能文档 |

## 依赖关系

```
stats.py
├── events.py (EventReader, ArtifactStore)
└── 标准库 (dataclasses, datetime, pathlib, typing)

runner.py
├── stats.py (TokenUsage, collect_stats, save_stats)
└── events.py

cli.py
├── stats.py (collect_stats)
└── runner.py
```
