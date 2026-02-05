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

#### 方式 A：从 PyPI 安装（推荐用户）

```bash
pip install simplerig
```

#### 方式 B：从源码安装（推荐开发者）

如果你需要修改源码或参与贡献：

```bash
git clone https://github.com/chaoshou-coder/simplerig.git
cd simplerig

# 创建并激活虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装开发依赖
pip install -e ".[dev]"
```

### 3. 运行第一个工作流

在你的项目根目录下：

```bash
# 1. 初始化配置 (可选，复制默认配置)
# cp /path/to/simplerig/config.yaml ./config.yaml

# 2. 运行任务
simplerig run "实现一个简单的用户登录接口，包含 JWT 认证"
```

## ⚙️ 配置指南

SimpleRig 的强大之处在于 `config.yaml`。你可以定义自己的 AI 团队：

```yaml
# config.yaml 示例

# 1. 定义模型 (支持 Cursor 内置模型或外部 API)
models:
  registry:
    cursor/gpt-5.2-high:
      provider: "cursor"
      context_limit: 272000
    opencode/kimi-k2.5:
      provider: "api"
      context_limit: 8000

# 2. 分配角色
  roles:
    architect: "cursor/gpt-5.2-high"  # 架构师
    dev: "cursor/gpt-5.2-high"        # 开发人员 (任务将按此模型的上下文限制拆分)

# 3. 配置工具链
tools:
  linter: "ruff"
  test_runner: "pytest"

# 4. 定义项目路径
project:
  source_dirs: ["src", "lib"]
```

更多配置详情请参考仓库内的 [config.yaml](./config.yaml)。

## 🛠️ CLI 命令行参考

| 命令 | 说明 | 示例 |
|------|------|------|
| `simplerig run <需?>` | 运行工作流 | `simplerig run "重构 auth 模块"` |
| `simplerig status` | 查看运行状态 | `simplerig status --run-id <id>` |
| `simplerig list` | 列出历史运行 | `simplerig list --limit 5` |
| `simplerig tail` | 实时查看事件流 | `simplerig tail --follow` |
| `simplerig stats` | 查看统计报告 | `simplerig stats --json` |

**常用参数：**
- `--dry-run`: 预演模式，仅规划不执行。
- `--resume`: 从最近一次失败或中断处继续。
- `--from-stage <stage>`: 从指定阶段（如 `develop`, `verify`）开始。

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

将 Skill 复制到 Cursor 配置目录，即可在 Chat 中使用 `/simplerig` 指令：

```bash
cp -r .cursor/skills/simplerig /path/to/your/project/.cursor/skills/
```

### OpenCode

```bash
cp -r .opencode/skills/simplerig /path/to/your/project/.opencode/skills/
```

## 📚 文档

- [技术架构文档](docs/architecture.md)

## 📄 许可证

[MIT License](LICENSE)
