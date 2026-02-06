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

在**你的项目目录**下安装 SimpleRig：

```bash
# 进入你的项目目录
cd /path/to/your/project

# 创建虚拟环境（如果还没有）
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

克隆 SimpleRig 并安装：

```bash
# 克隆到项目目录下（作为子目录）
git clone https://github.com/chaoshou-coder/simplerig.git

# 安装 simplerig 包
pip install -e ./simplerig

# 复制配置文件到项目根目录
cp ./simplerig/config.yaml ./config.yaml  # Linux/macOS
# Copy-Item .\simplerig\config.yaml .\config.yaml  # Windows PowerShell

# 验证安装
simplerig --help
```

安装后的目录结构：
```
your-project/
├── .venv/                # 虚拟环境
├── .cursor/skills/       # Skill 目录（下一步复制）
├── config.yaml           # 配置文件
├── simplerig/            # clone 的仓库
└── your-code/            # 你的代码
```

### 3. 使用方式

> **重要说明**：SimpleRig 是一个**Skill 驱动的工作流框架**，需要在 **Cursor 或 OpenCode 编辑器内**使用。编辑器内由 Agent 调用 `simplerig init/emit` 记录事件；CLI 也可手动执行这些命令。

#### 在 Cursor / OpenCode 中使用（推荐）

1. **复制 Skill 到你的项目**（见下方"编辑器集成"）
2. **在 Chat 中直接描述开发需求**(如果调用失败可在自然语言描述前加/simplerig强制cursor调用skill)，例如：
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

编辑器 Agent 会读取 SimpleRig Skill，按照框架定义的流程执行任务，并将产物写入 `simplerig_data/runs/<run_id>/artifacts/`。

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

SimpleRig 的强大之处在于 `config.yaml`。你可以定义自己的 AI 团队与模型角色：

```yaml
# config.yaml 示例

models:
  default_provider: "cursor"
  registry:
    cursor/opus-4.6-max:    # 架构/规划/救援
      provider: "cursor"
      context_limit: 200000
    cursor/auto:            # 验证（Cursor 自动选模型）
      provider: "cursor"
      context_limit: 200000
    cursor/gpt-5.2-codex-extra-high:
      provider: "cursor"
      context_limit: 272000
  roles:
    architect: "cursor/opus-4.6-max"   # 架构设计
    planner: "cursor/opus-4.6-max"     # 任务规划
    dev: "cursor/gpt-5.2-codex-extra-high"  # 开发实现（任务按此模型上下文拆分）
    verifier: "cursor/auto"            # 验证检查
    rescue: "cursor/opus-4.6-max"     # 救援修复

tools:
  linter: "ruff"
  test_runner: "pytest"

project:
  source_dirs: ["src", "lib"]
```

更多配置详情（API、超时、并行等）请参考仓库内的 [config.yaml](./config.yaml)。

## 🛠️ CLI 命令行参考

| 命令 | 说明 | 示例 |
|------|------|------|
| `simplerig init` | 初始化新 run | `simplerig init "需求"` |
| `simplerig emit` | 记录事件 | `simplerig emit stage.completed --stage plan --run-id <id>` |
| `simplerig list` | 列出历史运行 | `simplerig list --limit 5` |
| `simplerig status` | 查看运行状态 | `simplerig status --run-id <id>` |
| `simplerig tail` | 实时查看事件流 | `simplerig tail --follow` |
| `simplerig stats` | 查看统计报告 | `simplerig stats --json` |

> 注：如果 `simplerig` 命令不可用，可使用 `python -m simplerig.cli` 替代（如 `python -m simplerig.cli init "需求"`）。

## 📊 统计与产物

每次运行的产物存储在 `simplerig_data/runs/<run_id>/`：

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

### Token 统计记录

统计逻辑已实现（按阶段/任务/Run 汇总），但 **SimpleRig 不直接调用模型**，Token 数据需要由编辑器或 Agent 写入事件后才会显示：

```bash
# 记录一次 LLM 调用
simplerig emit llm.called --run-id <id> --prompt-tokens 1200 --completion-tokens 340

# 或在阶段完成时带上 token_usage
simplerig emit stage.completed --stage develop --run-id <id> --prompt-tokens 800 --completion-tokens 120
```

若从未写入任何 token 数据，`simplerig stats` 会显示「未记录」或 0。Skill 中可要求 Agent 在完成阶段时尽量附带 `--prompt-tokens` / `--completion-tokens`（若编辑器可提供）以得到真实消耗统计。

## 🧩 编辑器集成

### Cursor

1. **复制 Skill 到你的项目：**

   ```bash
   # Linux/macOS
   cp -r simplerig/.cursor/skills/ /path/to/your/project/.cursor/
   ```

   ```powershell
   # Windows PowerShell
   Copy-Item -Recurse simplerig\.cursor\skills\ \path\to\your\project\.cursor\
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
