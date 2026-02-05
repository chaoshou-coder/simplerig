"""
内置阶段处理器

提供默认的阶段实现，包括：
- plan: 任务规划
- develop: 代码开发
- verify: 代码验证 (LintGuard + 测试)
- integrate: 集成
"""
from pathlib import Path
from typing import Dict, Any, List

from .runner import Stage, StageStatus, StageResult, StageContext
from .lint_guard import LintGuard
from .events import ArtifactRef


def plan_handler(ctx: StageContext) -> StageResult:
    """
    规划阶段处理器
    
    职责：
    - 分析需求
    - 生成任务计划
    """
    # 生成规划（stub 实现，后续接 LLM）
    plan = {
        "requirement": ctx.requirement,
        "stages": ["plan", "develop", "verify", "integrate"],
        "tasks": [
            {
                "id": "task_analyze",
                "name": "需求分析",
                "description": f"分析需求: {ctx.requirement}",
                "parallel_group": 0,
            },
            {
                "id": "task_design",
                "name": "设计方案",
                "description": "设计实现方案",
                "dependencies": ["task_analyze"],
                "parallel_group": 1,
            },
            {
                "id": "task_implement",
                "name": "代码实现",
                "description": "实现代码",
                "dependencies": ["task_design"],
                "parallel_group": 2,
            },
        ],
        "stub": True,
    }
    
    ref = ctx.store.write("plan.json", plan)
    ctx.writer.emit("artifact.written", ctx.run_id, artifact=ref.to_dict())
    ctx.state.artifacts["plan.json"] = ref
    
    return StageResult(
        status=StageStatus.COMPLETED,
        outputs=[ref],
    )


def develop_handler(ctx: StageContext) -> StageResult:
    """
    开发阶段处理器
    
    职责：
    - 执行任务计划
    - 生成代码变更
    """
    # 读取计划（如果存在）
    plan = None
    if "plan.json" in ctx.inputs:
        try:
            plan = ctx.store.read_json("plan.json")
        except:
            pass
    
    # 生成代码变更（stub 实现）
    changes = {
        "requirement": ctx.requirement,
        "plan": plan,
        "changes": [
            {
                "file": "stub_file.py",
                "action": "create",
                "content": "# Stub implementation\n",
            }
        ],
        "stub": True,
    }
    
    ref = ctx.store.write("code_changes.json", changes)
    ctx.writer.emit("artifact.written", ctx.run_id, artifact=ref.to_dict())
    ctx.state.artifacts["code_changes.json"] = ref
    
    return StageResult(
        status=StageStatus.COMPLETED,
        outputs=[ref],
    )


def verify_handler(ctx: StageContext) -> StageResult:
    """
    验证阶段处理器
    
    职责：
    - 运行 LintGuard (linter + formatter)
    - 运行测试
    - 生成验证报告
    """
    # 初始化 LintGuard
    guard = LintGuard(project_root=str(ctx.run_dir.parent.parent.parent), config=ctx.config)
    
    # 运行 lint 检查
    lint_success, lint_report = guard.must_pass()
    
    # 生成验证结果
    verify_result = {
        "requirement": ctx.requirement,
        "lint": {
            "success": lint_success,
            "report": lint_report,
        },
        "tests": {
            "success": True,  # stub
            "report": "Tests skipped (stub)",
        },
        "overall_success": lint_success,
    }
    
    ref = ctx.store.write("verify_result.json", verify_result)
    ctx.writer.emit("artifact.written", ctx.run_id, artifact=ref.to_dict())
    ctx.state.artifacts["verify_result.json"] = ref
    
    if not lint_success:
        return StageResult(
            status=StageStatus.FAILED,
            outputs=[ref],
            error=f"Lint check failed: {lint_report}",
        )
    
    return StageResult(
        status=StageStatus.COMPLETED,
        outputs=[ref],
    )


def integrate_handler(ctx: StageContext) -> StageResult:
    """
    集成阶段处理器
    
    职责：
    - 应用代码变更
    - 生成集成报告
    """
    # 读取验证结果
    verify_result = None
    if "verify_result.json" in ctx.inputs:
        try:
            verify_result = ctx.store.read_json("verify_result.json")
        except:
            pass
    
    # 检查验证是否通过
    if verify_result and not verify_result.get("overall_success", False):
        return StageResult(
            status=StageStatus.FAILED,
            error="Cannot integrate: verification failed",
        )
    
    # 生成集成结果（stub 实现）
    integration_result = {
        "requirement": ctx.requirement,
        "verify_result": verify_result,
        "integration": {
            "applied_changes": [],
            "commit_hash": None,
        },
        "stub": True,
    }
    
    ref = ctx.store.write("integration_result.json", integration_result)
    ctx.writer.emit("artifact.written", ctx.run_id, artifact=ref.to_dict())
    ctx.state.artifacts["integration_result.json"] = ref
    
    return StageResult(
        status=StageStatus.COMPLETED,
        outputs=[ref],
    )


# ========== 预定义阶段 ==========

def get_default_stages() -> List[Stage]:
    """获取默认阶段列表"""
    return [
        Stage(
            name="plan",
            handler=plan_handler,
            outputs=["plan.json"],
        ),
        Stage(
            name="develop",
            handler=develop_handler,
            depends_on=["plan"],
            required_inputs=["plan.json"],
            outputs=["code_changes.json"],
        ),
        Stage(
            name="verify",
            handler=verify_handler,
            depends_on=["develop"],
            required_inputs=["code_changes.json"],
            outputs=["verify_result.json"],
        ),
        Stage(
            name="integrate",
            handler=integrate_handler,
            depends_on=["verify"],
            required_inputs=["verify_result.json"],
            outputs=["integration_result.json"],
        ),
    ]
