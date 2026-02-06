"""
内置阶段处理器

提供默认的阶段实现，包括：
- plan: 任务规划
- develop: 代码开发（可选 TDD 模式）
- verify: 代码验证 (LintGuard + 测试 + 可选 BDD)
- integrate: 集成
"""
from pathlib import Path
from typing import List

from .runner import Stage, StageStatus, StageResult, StageContext
from .lint_guard import LintGuard


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
    - 执行任务计划，生成代码变更
    - 若 options.tdd 且 plan 中有 tdd_test_file/tdd_impl_file，则执行 TDDRunner 红绿循环（dev_func 可从 options 注入）
    """
    plan = None
    if "plan.json" in ctx.inputs:
        try:
            plan = ctx.store.read_json("plan.json")
        except Exception:
            pass

    tdd_mode = ctx.options.get("tdd", False)
    project_root = Path(ctx.run_dir.parent.parent.parent)
    tdd_ran = False
    tdd_success = True

    if tdd_mode and plan:
        tdd_test = plan.get("tdd_test_file")
        if not tdd_test and plan.get("tasks"):
            for t in plan.get("tasks", []):
                if t.get("test_file"):
                    tdd_test = t.get("test_file")
                    break
        tdd_impl = plan.get("tdd_impl_file")
        if not tdd_impl and plan.get("tasks"):
            for t in plan.get("tasks", []):
                if t.get("impl_file"):
                    tdd_impl = t.get("impl_file")
                    break
        if tdd_test and tdd_impl:
            from .tdd import TDDRunner
            test_path = project_root / tdd_test if not (project_root / tdd_test).is_absolute() else Path(tdd_test)
            impl_path = project_root / tdd_impl if not (project_root / tdd_impl).is_absolute() else Path(tdd_impl)
            dev_func = ctx.options.get("tdd_dev_func") or (lambda: None)
            runner = TDDRunner(ctx.config, ctx.writer, ctx.run_id)
            tdd_result = runner.run_cycle(test_path, impl_path, dev_func, project_root=project_root)
            tdd_ran = True
            tdd_success = tdd_result.success

    changes = {
        "requirement": ctx.requirement,
        "plan": plan,
        "tdd_mode": tdd_mode,
        "tdd_ran": tdd_ran,
        "tdd_success": tdd_success if tdd_ran else None,
        "changes": [
            {
                "file": "stub_file.py",
                "action": "create",
                "content": "# Stub implementation\n",
            }
        ],
        "stub": not tdd_ran,
    }

    ref = ctx.store.write("code_changes.json", changes)
    ctx.writer.emit("artifact.written", ctx.run_id, artifact=ref.to_dict())
    ctx.state.artifacts["code_changes.json"] = ref

    if tdd_ran and not tdd_success:
        return StageResult(
            status=StageStatus.FAILED,
            outputs=[ref],
            error="TDD cycle failed (green phase)",
        )
    return StageResult(status=StageStatus.COMPLETED, outputs=[ref])


def verify_handler(ctx: StageContext) -> StageResult:
    """
    验证阶段处理器

    职责：
    - 运行 LintGuard (linter + formatter)
    - 运行测试（exit 5 视为跳过）
    - 若 artifacts 下有 .feature 或启用 bdd，则执行 BDDRunner，结果写入 bdd 字段
    - 生成验证报告
    """
    project_root = ctx.run_dir.parent.parent.parent
    guard = LintGuard(
        project_root=str(project_root),
        config=ctx.config,
        writer=ctx.writer,
        run_id=ctx.run_id,
    )
    check = guard.full_check()
    lint_result = check["lint"]
    test_result = check["tests"]
    lint_success = lint_result.success
    lint_report = lint_result.stdout or lint_result.stderr or "Lint check completed"
    tests_success = test_result.success
    tests_report = test_result.stdout or test_result.stderr or "Tests completed"
    bdd_result = None

    # BDD: 当 artifacts 下有 .feature 或 options.bdd 时执行
    feature_files = list(Path(ctx.store.artifacts_dir).glob("*.feature")) if ctx.store.artifacts_dir.exists() else []
    if (ctx.options.get("bdd") or feature_files) and feature_files:
        from .bdd import BDDRunner
        bdd_runner = BDDRunner(ctx.config, ctx.writer, ctx.run_id, store=ctx.store)
        for fp in feature_files:
            result = bdd_runner.run_feature(fp)
            report_text = bdd_runner.generate_report(result, "text", store=ctx.store)
            bdd_runner.generate_report(result, "json", store=ctx.store)
            bdd_result = {
                "feature": result.feature_name,
                "passed": result.passed,
                "duration_ms": result.duration_ms,
                "report": report_text,
            }
            if not result.passed:
                tests_success = False
                tests_report = report_text

    verify_result = {
        "requirement": ctx.requirement,
        "lint": {"success": lint_success, "report": lint_report},
        "tests": {"success": tests_success, "report": tests_report},
        "bdd": bdd_result,
        "overall_success": lint_success and tests_success,
    }

    ref = ctx.store.write("verify_result.json", verify_result)
    ctx.writer.emit("artifact.written", ctx.run_id, artifact=ref.to_dict())
    ctx.state.artifacts["verify_result.json"] = ref

    if not verify_result["overall_success"]:
        return StageResult(
            status=StageStatus.FAILED,
            outputs=[ref],
            error=f"Verify failed: lint={lint_success}, tests={tests_success}",
        )
    return StageResult(status=StageStatus.COMPLETED, outputs=[ref])


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
        except Exception:
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


def get_enhanced_stages() -> List[Stage]:
    """获取启用 TDD/BDD 的阶段列表（与 get_default_stages 相同，通过 run(tdd=..., bdd=...) 启用）"""
    return get_default_stages()
