---
name: simplerig
description: SimpleRig 多 Agent 工作流框架。在用户提出开发需求时使用，完全可配置，解决硬编码问题。
---

# SimpleRig

## 何时使用

- 用户提出完整开发需求时
- 需要多 Agent 并行开发时
- 需要自动代码风格检查时

## Instructions（Agent 必须执行）

1. **检查安装**：确认 `simplerig` 已安装
2. **检查配置**：确认项目根目录有 `config.yaml`（或环境变量 `SIMPLERIG_CONFIG`）
3. **获取需求**：如果用户未明确需求，先询问
4. **执行工作流**：在项目根目录运行：
   ```bash
   simplerig run "用户的完整需求描述"
   ```
5. **反馈结果**：将执行结果摘要反馈给用户

## 配置检查

执行前请确认：
- `config.yaml` 存在或 `SIMPLERIG_CONFIG` 已设置
- 模型配置正确（`models.registry` 和 `models.roles`）
- API key 已配置（`api.openrouter.key` 或环境变量）

## 输出

工作流会输出：
- 生成的代码文件路径
- 测试执行结果
- Lint 检查结果
- 成本统计（如启用）
