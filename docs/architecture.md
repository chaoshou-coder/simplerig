# SimpleRig 技术架构文档

> 版本: 1.0.0
> 更新日期: 2026-02-05

## 1. 架构概览

SimpleRig 是一个基于 **Event Sourcing（事件溯源）** 的多 Agent 工作流框架。与传统的状态机框架不同，SimpleRig 将所有状态变更记录为不可变的事件流，从而实现了审计、回放、断点续传和精确的统计分析。

### 核心组件分层

```mermaid
graph TD
    User[用户 / CLI] --> API[SimpleRig API / CLI Entry]
    
    subgraph Core [核心层]
        Planner[智能规划器]
        Scheduler[任务调度器]
        Runner[任务执行器]
    end
    
    subgraph State [状态层]
        EventManager[事件管理器]
        ArtifactStore[产物存储]
        LockManager[分布式锁]
    end
    
    subgraph Infrastructure [基础设施]
        LLM[模型注册表 (Cursor/API)]
        Tools[工具链 (Ruff/Pytest)]
        FS[文件系统]
    end

    API --> Planner
    API --> Scheduler
    Planner --> Scheduler
    Scheduler --> Runner
    Runner --> EventManager
    Runner --> Tools
    Runner --> LLM
    EventManager --> FS
```

## 2. 核心机制详解

### 2.1 事件溯源 (Event Sourcing)

SimpleRig 的“事实源（Source of Truth）”不是内存中的对象，而是磁盘上的 `events.jsonl` 文件。

*   **存储格式**：JSON Lines。每行一个完整的事件对象。
*   **事件结构**：
    ```json
    {
      "seq": 105,
      "type": "task.completed",
      "timestamp": "2026-02-05T10:00:00Z",
      "run_id": "abc-123",
      "data": {
        "task_id": "task_auth_01",
        "result": "success",
        "output_files": ["src/auth.py"]
      }
    }
    ```
*   **优势**：
    *   **可恢复性**：程序崩溃后，只需重读 `events.jsonl` 即可完美重建内存状态。
    *   **可观测性**：`simplerig tail` 实际上就是实时读取这个文件。
    *   **解耦统计**：统计模块只需消费事件流，无需侵入业务逻辑。

### 2.2 智能任务规划 (Context-Aware Planning)

为了解决“规划出的任务太大，执行模型吃不下”的问题，SimpleRig 引入了基于执行模型能力的规划机制。

1.  **读取配置**：获取 `roles.dev` 指向的执行模型（如 `cursor/gpt-5.2-codex`）。
2.  **获取约束**：读取该模型的 `context_limit` 和 `safe_limit`（通常为上限的 50%-70%）。
3.  **动态Prompt**：在规划阶段，Prompt 会显式包含：“请将任务拆分为若干子任务，每个子任务涉及的代码量和上下文不得超过 X tokens”。

### 2.3 任务调度与并行 (DAG Scheduler)

调度器维护一个内存中的 DAG（有向无环图）。

*   **状态流转**：
    *   `PENDING`: 等待前置依赖完成。
    *   `READY`: 依赖已满足，进入就绪队列。
    *   `RUNNING`: 已分配 Worker 执行中。
    *   `COMPLETED` / `FAILED`: 终态。
*   **并发控制**：
    *   使用 `ThreadPoolExecutor` 实现多线程并发。
    *   并发数受 `config.yaml` 中的 `parallel.max_agents` 限制。
    *   **Tool Lock**：某些非线程安全的工具（如某些文件操作）会自动加锁。

### 2.4 断点续传 (Resume Capability)

得益于事件溯源，断点续传的实现非常优雅：

1.  用户执行 `simplerig run --resume`。
2.  系统读取 `events.jsonl`，在内存中重放所有事件。
3.  重放结束后，调度器检查 DAG 中所有任务的状态。
4.  **跳过**已 `COMPLETED` 的任务。
5.  **重置** `RUNNING`（但实际已中断）的任务为 `READY`。
6.  继续调度循环。

## 3. 数据流与产物

工作流执行过程中会产生多种数据，分层存储于 `.simplerig/runs/<run_id>/`：

| 目录/文件 | 说明 | 格式 |
|---|---|---|
| `events.jsonl` | **核心**：完整的操作流水日志 | JSONL |
| `artifacts/plan.json` | 架构师/规划师生成的原始计划 | JSON |
| `artifacts/code_changes.json` | 记录所有文件的修改差异 (Diff) | JSON |
| `artifacts/verify_result.json` | 测试运行器和 Linter 的输出 | JSON |
| `artifacts/stats.json` | 运行结束时生成的统计摘要 | JSON |
| `locks/run.lock` | 防止同一 Run ID 被并发写入的文件锁 | Empty File |

## 4. 扩展性设计

### 4.1 模型适配器 (Model Adapters)

SimpleRig 通过 Adapter 模式屏蔽了不同 LLM Provider 的差异：

*   **OpenAI/Compatible API**：标准的 Request/Response 处理。
*   **Cursor Native**：通过特殊的伪协议或本地 Agent 交互（依赖 Cursor IDE 环境）。

### 4.2 工具链抽象 (Toolchain Abstraction)

Linter 和 Test Runner 是可插拔的。只要在 `config.yaml` 中配置了对应的命令格式，理论上支持任意语言的工具链：

```yaml
tools:
  linter: "eslint"  # JS/TS
  linter_args: ["--fix"]
```

框架只负责：
1.  构造 subprocess 命令。
2.  捕获 stdout/stderr。
3.  解析 Exit Code（0 为成功，非 0 为失败）。

---

*文档维护者: SimpleRig Team*
