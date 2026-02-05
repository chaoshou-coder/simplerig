# SimpleRig

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**SimpleRig** 是一个高度可配置的**多 Agent 工作流框架**，专为 AI 辅助编程设计。它支持 **Cursor** 和 **OpenCode**，通过事件溯源、任务并行和断点续传等机制，让复杂的 AI 开发任务变得可控、可观测、可复现。

---

## ✨ 核心特性

- **完全可配置**：拒绝硬编码。模型（支持 Cursor 内置模型 & 外部 API）、工具链（Linter/Formatter/Test）、角色分配、超时策略全由 `config.yaml` 定义。
- **任务级并行**：基于 DAG 的依赖调度，支持多 Agent 并行开发，内置并发上限控制与失败隔离。
- **JSONL 事件溯源**：系统运行的一切（任务状态、代码变更、工具调用）皆记录为事件。可审计、可重放、可调试。
- **断点续传**：支持从任意中断点（`--resume`）或指定阶段（`--from-stage`）恢复运行，节省时间和 Token。
- **智能上下文管理**：根据**执行模型**的实际上下文窗口（Context Window）自动规划和拆分任务，避免模型过载。
- **质量门禁**：内置 TDD（测试驱动开发）与 Lint 检查，红绿测试循环，确保代码质量。
- **详细统计**：提供精确的耗时、Token 消耗统计（按阶段/任务/Run），支持 JSON 导出。

## 🚀 快速开始

### 1. 前置要求

- **Python 3.10+**
- (可选) Cursor 或 OpenCode 编辑器（用于集成 Agent Skills）

### 2. 安装

从 GitHub 克隆并安装：

```bash
git clone https://github.com/chaoshou-coder/simplerig.git
cd simplerig

# 创建虚拟环境
python -m venv .venv
```

激活虚拟环境：

```bash
# Linux/macOS
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.venv\Scripts\Activate
```

```cmd
# Windows CMD
.venv\Scripts\activate.bat
```

安装并验证：

```bash
# 安装（含开发依赖）
pip install -e ".[dev]"

# 验证
simplerig --help
```

### 3. 使用方式

> **重要说明**：SimpleRig 是一个**Skill 驱动的工作流框架**，需要在 **Cursor 或 OpenCode 编辑器内**使用。编辑器内由 Agent 调用 `simplerig init/emit` 记录事件；CLI 也可手动执行这些命令。

#### 在 Cursor / OpenCode 中使用（推荐）

1. **复制 Skill 到你的项目**（见下方"编辑器集成"）
2. **在 Chat 中直接描述开发需求**，例如：
   - "帮我实现一个用户注册功能，要有邮箱验证"
   - "把这个模块重构成单例模式"
   - "给 auth 模块添加完整的单元测试"

3. Agent 会自动执行以下流程并记录事件：
   ```bash
   simplerig init "实现用户认证功能"
   # 规划 → 开发 → 验证 → 完成
   simplerig emit stage.completed --stage plan --run-id <run_id>
   simplerig emit stage.completed --stage develop --run-id <run_id>
   simplerig emit stage.completed --stage verify --run-id <run_id>
   simplerig emit run.completed --run-id <run_id>
   ```

编辑器 Agent 会读取 SimpleRig Skill，按照框架定义的流程执行任务，并将产物写入 `.simplerig/runs/<run_id>/artifacts/`。

#### CLI 辅助命令

CLI 可用于初始化 run、记录事件以及查看状态/统计：

```bash
# 初始化 run
simplerig init "实现用户认证功能"

# 记录阶段完成事件
simplerig emit stage.completed --stage plan --run-id <id>

# 查看历史运行
simplerig list

# 查看运行状态
simplerig status --run-id <id>

# 查看统计报告
simplerig stats
```

## ⚙️ 配置指南

SimpleRig 的强大之处在于 `config.yaml`。你可以定义自己的 AI 团队：

```yaml
# config.yaml 示例

# 模型配置
models:
  # 模型注册表
  registry:
    cursor/gpt-5.2-high:
      provider: "cursor"
      context_limit: 272000
    opencode/kimi-k2.5:
      provider: "api"
      context_limit: 8000
  # 角色分配
  roles:
    architect: "cursor/gpt-5.2-high"  # 架构师
    dev: "cursor/gpt-5.2-high"        # 开发 (任务按此模型上下文拆分)

# 工具链配置
tools:
  linter: "ruff"
  test_runner: "pytest"

# 项目路径
project:
  source_dirs: ["src", "lib"]
```

更多配置详情请参考仓库内的 [config.yaml](./config.yaml)。

## 🛠️ CLI 命令行参考

| 命令 | 说明 | 示例 |
|------|------|------|
| `simplerig init` | 初始化新 run | `simplerig init "需求"` |
| `simplerig emit` | 记录事件 | `simplerig emit stage.completed --stage plan --run-id <id>` |
| `simplerig list` | 列出历史运行 | `simplerig list --limit 5` |
| `simplerig status` | 查看运行状态 | `simplerig status --run-id <id>` |
| `simplerig tail` | 实时查看事件流 | `simplerig tail --follow` |
| `simplerig stats` | 查看统计报告 | `simplerig stats --json` |

> 注：在编辑器内使用 Skill 时，Agent 通过 `init/emit` 记录事件；`simplerig run` 仍可用于本地演示/调试框架阶段机（stub 逻辑）。

## 📊 统计与产物

每次运行的产物存储在 `.simplerig/runs/<run_id>/`：

- **`events.jsonl`**: 事实源，包含所有操作记录。
- **`artifacts/`**:
  - `plan.json`: 架构设计与任务规划。
  - `code_changes.json`: 代码变更记录。
  - `stats.json`: 详细的耗时与 Token 统计。

查看统计报告：
```bash
simplerig stats
```
输出示例：
```text
【总体统计】
  总耗时: 5m 23.4s
  总 Token: 15,234 (输入 12k / 输出 3k)
【阶段统计】
  plan: 12s, 1.2k tokens
  develop: 4m, 8.7k tokens
```

## 🧩 编辑器集成

### Cursor

1. **复制 Skill 到你的项目：**

   ```bash
   # Linux/macOS
   cp -r .cursor/skills/simplerig /path/to/your/project/.cursor/skills/
   ```

   ```powershell
   # Windows PowerShell
   Copy-Item -Recurse .cursor\skills\simplerig \path\to\your\project\.cursor\skills\
   ```

2. **在 Cursor Chat 中使用：**
   - 直接输入开发需求（如 "实现用户认证功能"），Cursor 会自动调用 SimpleRig
   - 或使用 `/simplerig` 指令显式触发

3. **工作流程：** Cursor Agent 读取 Skill → 理解你的需求 → 调用 SimpleRig 规划任务 → 并行执行开发

### OpenCode

1. **复制 Skill 到你的项目：**

   ```bash
   # Linux/macOS
   cp -r .opencode/skills/simplerig /path/to/your/project/.opencode/skills/
   ```

   ```powershell
   # Windows PowerShell
   Copy-Item -Recurse .opencode\skills\simplerig \path\to\your\project\.opencode\skills\
   ```

2. **在 OpenCode 中使用：** 直接用自然语言描述开发任务即可

## 📚 文档

- [技术架构文档](docs/architecture.md)

## 📄 许可证

[MIT License](LICENSE)
