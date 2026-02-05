---
name: simplerig
description: SimpleRig 多 Agent 工作流框架。在用户提出开发需求时使用，支持 JSONL 事件溯源、任务级并行、断点续传。
---

# SimpleRig

## 何时使用

- 用户提出完整开发需求时
- 需要多 Agent 并行开发时
- 需要断点续传/恢复执行时
- 需要自动代码风格检查时

## Instructions（Agent 必须执行）

1. **检查安装**：确认 `simplerig` 已安装
   ```bash
   pip show simplerig
   ```

2. **检查配置**：确认项目根目录有 `config.yaml`

3. **获取需求**：如果用户未明确需求，先询问

4. **执行工作流**：
   ```bash
   # 新建运行
   simplerig run "用户的完整需求描述"
   
   # 预演模式
   simplerig run "需求" --dry-run
   
   # 从中断恢复
   simplerig run --resume
   
   # 从指定阶段开始
   simplerig run "需求" --from-stage develop
   ```

5. **查看状态**：
   ```bash
   # 查看运行状态
   simplerig status
   
   # 查看事件流
   simplerig tail --follow
   
   # 列出历史
   simplerig list
   ```

6. **反馈结果**：将执行结果摘要反馈给用户

## Run 目录结构

执行后会创建：
```
.simplerig/runs/<run_id>/
├── events.jsonl      # 事件流（事实源，可审计）
├── artifacts/        # 产物目录
│   ├── plan.json           # 规划产物
│   ├── code_changes.json   # 代码变更
│   ├── verify_result.json  # 验证结果
│   └── task_*.result.json  # 任务输出
└── locks/
    └── run.lock      # 互斥锁
```

## 配置检查

执行前请确认：
- `config.yaml` 存在或 `SIMPLERIG_CONFIG` 已设置
- 模型配置正确（`models.registry` 和 `models.roles`）
- 可选：API key（`api.openrouter.key` 或环境变量）

## 核心功能

### 断点续传
```bash
# 中断后恢复
simplerig run --resume

# 从指定 run 恢复
simplerig run --resume <run_id>
```

### 任务级并行
- 无依赖的任务自动并行执行
- 可配置最大并发数 `parallel.max_agents`
- 失败隔离：某任务失败不影响其他任务

### 事件溯源
- 所有操作记录为 `events.jsonl`
- 可通过事件流重建任何时刻的状态
- 支持事件过滤：`simplerig tail --filter "task.*"`

## 输出

工作流会输出：
- 事件日志：`.simplerig/runs/<run_id>/events.jsonl`
- 产物目录：`.simplerig/runs/<run_id>/artifacts/`
- 控制台：执行状态、完成阶段、失败阶段
