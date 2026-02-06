"""
Runner - 阶段机与断点续传

核心组件：
- Stage: 阶段定义
- StageMachine: 瀑布流阶段机
- StateReconstructor: 从事件流重建状态
- ResumeStrategy: 断点续传策略
"""
import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .events import (
    Event,
    EventWriter,
    EventReader,
    ArtifactStore,
    ArtifactRef,
    create_run_context,
)
from .config import get_config
from .stats import TokenUsage, collect_stats, save_stats


# ========== 阶段定义 ==========

class StageStatus(enum.Enum):
    """阶段状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """阶段执行结果"""
    status: StageStatus
    outputs: List[ArtifactRef] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: int = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass
class Stage:
    """阶段定义"""
    name: str                           # 阶段名称
    handler: Callable = None            # 执行函数 (context) -> StageResult
    depends_on: List[str] = field(default_factory=list)  # 依赖的阶段
    required_inputs: List[str] = field(default_factory=list)  # 需要的输入 artifacts
    outputs: List[str] = field(default_factory=list)  # 产出的 artifacts


# ========== 状态重建 ==========

@dataclass
class RunState:
    """Run 状态（从事件流重建）"""
    run_id: str
    requirement: str = ""
    status: str = "unknown"
    current_stage: str = ""
    completed_stages: Set[str] = field(default_factory=set)
    failed_stages: Set[str] = field(default_factory=set)
    skipped_stages: Set[str] = field(default_factory=set)
    artifacts: Dict[str, ArtifactRef] = field(default_factory=dict)
    tasks: Dict[str, dict] = field(default_factory=dict)
    last_event_seq: int = 0
    start_time: str = ""
    end_time: str = ""
    
    def is_stage_done(self, stage_name: str) -> bool:
        """检查阶段是否已完成（或跳过）"""
        return stage_name in self.completed_stages or stage_name in self.skipped_stages
    
    def can_skip(self, stage: Stage, artifact_store: ArtifactStore) -> bool:
        """
        判断是否可以跳过阶段
        
        条件：
        1. 阶段已完成
        2. 所有输出 artifacts 存在且校验通过
        """
        if stage.name not in self.completed_stages:
            return False
        
        # 检查输出 artifacts
        for output_name in stage.outputs:
            if output_name not in self.artifacts:
                return False
            
            ref = self.artifacts[output_name]
            if not artifact_store.verify(ref):
                return False
        
        return True


class StateReconstructor:
    """从事件流重建状态"""
    
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.reader = EventReader(run_dir)
    
    def reconstruct(self) -> RunState:
        """重建状态"""
        state = RunState(run_id=self.run_dir.name)
        
        for event in self.reader.iter_events():
            self._process_event(state, event)
        
        return state
    
    def _process_event(self, state: RunState, event: Event):
        """处理单个事件"""
        state.last_event_seq = event.seq
        
        if event.type == "run.started":
            state.status = "running"
            state.requirement = event.data.get("requirement", "")
            state.start_time = event.timestamp
        
        elif event.type == "run.completed":
            state.status = "completed"
            state.end_time = event.timestamp
        
        elif event.type == "run.failed":
            state.status = "failed"
            state.end_time = event.timestamp
        
        elif event.type == "run.aborted":
            state.status = "aborted"
            state.end_time = event.timestamp
        
        elif event.type == "stage.started":
            state.current_stage = event.data.get("stage", "")
        
        elif event.type == "stage.completed":
            stage_name = event.data.get("stage", "")
            state.completed_stages.add(stage_name)
            if state.current_stage == stage_name:
                state.current_stage = ""
        
        elif event.type == "stage.failed":
            stage_name = event.data.get("stage", "")
            state.failed_stages.add(stage_name)
        
        elif event.type == "stage.skipped":
            stage_name = event.data.get("stage", "")
            state.skipped_stages.add(stage_name)
        
        elif event.type == "artifact.written":
            artifact_data = event.data.get("artifact", {})
            if "ref" in artifact_data:
                # 提取文件名作为 key
                name = artifact_data["ref"].replace("artifacts/", "")
                state.artifacts[name] = ArtifactRef(
                    ref=artifact_data.get("ref", ""),
                    sha256=artifact_data.get("sha256", ""),
                    size=artifact_data.get("size", 0),
                    mime=artifact_data.get("mime", "application/octet-stream"),
                )
        
        elif event.type == "task.created":
            task_id = event.data.get("task_id", "")
            state.tasks[task_id] = {
                "status": "pending",
                "data": event.data,
            }
        
        elif event.type == "task.started":
            task_id = event.data.get("task_id", "")
            if task_id in state.tasks:
                state.tasks[task_id]["status"] = "running"
        
        elif event.type == "task.completed":
            task_id = event.data.get("task_id", "")
            if task_id in state.tasks:
                state.tasks[task_id]["status"] = "completed"
                state.tasks[task_id]["output"] = event.data.get("output")
        
        elif event.type == "task.failed":
            task_id = event.data.get("task_id", "")
            if task_id in state.tasks:
                state.tasks[task_id]["status"] = "failed"
                state.tasks[task_id]["error"] = event.data.get("error")
        
        elif event.type == "task.skipped":
            task_id = event.data.get("task_id", "")
            if task_id in state.tasks:
                state.tasks[task_id]["status"] = "skipped"


# ========== 阶段机上下文 ==========

@dataclass
class StageContext:
    """阶段执行上下文"""
    run_id: str
    run_dir: Path
    writer: EventWriter
    store: ArtifactStore
    state: RunState
    config: Any
    requirement: str = ""
    options: Dict[str, Any] = field(default_factory=dict)

    # 当前阶段信息
    stage_name: str = ""
    inputs: Dict[str, ArtifactRef] = field(default_factory=dict)


# ========== 阶段机 ==========

class StageMachine:
    """
    瀑布流阶段机
    
    支持：
    - 阶段依赖
    - 断点续传 (--resume)
    - 从指定阶段开始 (--from-stage)
    - 阶段跳过 (基于产物校验)
    """
    
    # 默认阶段定义
    DEFAULT_STAGES = [
        Stage(name="plan", outputs=["plan.json"]),
        Stage(name="develop", depends_on=["plan"], required_inputs=["plan.json"], outputs=["code_changes.json"]),
        Stage(name="verify", depends_on=["develop"], required_inputs=["code_changes.json"], outputs=["verify_result.json"]),
        Stage(name="integrate", depends_on=["verify"], required_inputs=["verify_result.json"], outputs=["integration_result.json"]),
    ]
    
    def __init__(
        self,
        run_dir: Path,
        stages: List[Stage] = None,
        fail_fast: bool = False,
    ):
        self.run_dir = Path(run_dir)
        self.stages = stages or self.DEFAULT_STAGES
        self.fail_fast = fail_fast
        
        # 创建上下文
        self.writer, self.store, self.lock = create_run_context(run_dir)
        
        # 阶段名称到阶段的映射
        self._stage_map = {s.name: s for s in self.stages}
    
    def run(
        self,
        requirement: str = "",
        resume: bool = False,
        from_stage: str = None,
        tdd: bool = False,
        bdd: bool = False,
    ) -> RunState:
        """
        执行阶段机
        
        Args:
            requirement: 需求描述（新 run）
            resume: 是否恢复执行
            from_stage: 从指定阶段开始
            
        Returns:
            最终状态
        """
        config = get_config()
        lock_timeout = config.timeouts.get("run_lock", 30)
        if lock_timeout is not None and lock_timeout <= 0:
            lock_timeout = None
        
        if not self.lock.acquire(timeout=lock_timeout):
            raise TimeoutError(f"获取运行锁超时（{lock_timeout}s）")
        
        try:
            # 重建状态
            reconstructor = StateReconstructor(self.run_dir)
            state = reconstructor.reconstruct()
            
            # 确定执行策略
            if resume:
                # 恢复模式：从上次中断处继续
                if state.status == "completed":
                    return state  # 已完成，无需继续
                
                if not state.requirement and not requirement:
                    raise ValueError("无法恢复：缺少需求描述")
                
                requirement = state.requirement or requirement
            else:
                # 新执行模式
                if not requirement:
                    raise ValueError("缺少需求描述")
                
                # 写入 run.started 事件
                self.writer.emit(
                    "run.started",
                    self.run_dir.name,
                    requirement=requirement,
                )
                state.requirement = requirement
                state.status = "running"
            
            # 确定起始阶段
            start_idx = 0
            if from_stage:
                if from_stage not in self._stage_map:
                    raise ValueError(f"未知阶段: {from_stage}")
                start_idx = next(
                    i for i, s in enumerate(self.stages) 
                    if s.name == from_stage
                )
                
                # 标记之前的阶段为跳过
                for i in range(start_idx):
                    stage = self.stages[i]
                    if not state.is_stage_done(stage.name):
                        self._skip_stage(state, stage, "from_stage 跳过")
            
            # 创建执行上下文
            ctx = StageContext(
                run_id=self.run_dir.name,
                run_dir=self.run_dir,
                writer=self.writer,
                store=self.store,
                state=state,
                config=config,
                requirement=requirement,
                options={"tdd": tdd, "bdd": bdd},
            )
            
            # 执行各阶段
            for i in range(start_idx, len(self.stages)):
                stage = self.stages[i]
                
                # 检查是否可以跳过
                if state.can_skip(stage, self.store):
                    self._skip_stage(state, stage, "产物校验通过")
                    continue
                
                # 检查是否已完成但产物不完整（脏恢复）
                if stage.name in state.completed_stages:
                    # 需要重新执行
                    state.completed_stages.discard(stage.name)
                
                # 检查是否失败（需要重试）
                if stage.name in state.failed_stages and resume:
                    state.failed_stages.discard(stage.name)
                
                # 执行阶段
                result = self._execute_stage(ctx, stage)
                
                if result.status == StageStatus.FAILED:
                    if self.fail_fast:
                        self.writer.emit(
                            "run.failed",
                            self.run_dir.name,
                            error=result.error,
                            stage=stage.name,
                        )
                        state.status = "failed"
                        return state
            
            # 检查是否全部完成
            all_done = all(
                state.is_stage_done(s.name) 
                for s in self.stages
            )
            
            if all_done:
                # 收集统计信息
                run_stats = collect_stats(self.run_dir)
                
                # 写入 run.completed 事件（包含统计摘要）
                self.writer.emit(
                    "run.completed", 
                    self.run_dir.name,
                    stats={
                        "total_duration_ms": run_stats.total_duration_ms,
                        "total_token_usage": run_stats.total_token_usage.to_dict(),
                        "stages": {k: v.to_dict() for k, v in run_stats.stages.items()},
                    },
                )
                
                # 保存统计到 artifacts
                save_stats(self.run_dir, run_stats)
                
                state.status = "completed"
            
            return state
        finally:
            self.lock.release()
    
    def _skip_stage(self, state: RunState, stage: Stage, reason: str):
        """跳过阶段"""
        self.writer.emit(
            "stage.skipped",
            self.run_dir.name,
            stage=stage.name,
            reason=reason,
        )
        state.skipped_stages.add(stage.name)
    
    def _execute_stage(self, ctx: StageContext, stage: Stage) -> StageResult:
        """执行单个阶段"""
        import time
        start_time = time.time()
        
        # 更新上下文
        ctx.stage_name = stage.name
        ctx.inputs = {
            name: ctx.state.artifacts.get(name)
            for name in stage.required_inputs
            if name in ctx.state.artifacts
        }
        
        # 阶段 -> 角色 -> 模型名称 映射
        _stage_role = {"plan": "planner", "develop": "dev", "verify": "verifier", "integrate": "verifier"}
        _role = _stage_role.get(stage.name, "dev")
        _model = ctx.config.roles.get(_role, "unknown")

        # 写入 stage.started 事件（含模型名称）
        self.writer.emit(
            "stage.started",
            self.run_dir.name,
            stage=stage.name,
            model=_model,
            inputs=list(ctx.inputs.keys()),
        )
        
        try:
            # 执行阶段处理器
            if stage.handler:
                result = stage.handler(ctx)
            else:
                # 默认 stub handler
                result = self._stub_handler(ctx, stage)
            
            duration_ms = int((time.time() - start_time) * 1000)
            result.duration_ms = duration_ms
            
            if result.status == StageStatus.COMPLETED:
                # 写入 stage.completed 事件
                self.writer.emit(
                    "stage.completed",
                    self.run_dir.name,
                    stage=stage.name,
                    outputs=[ref.to_dict() for ref in result.outputs],
                    duration_ms=duration_ms,
                    token_usage=result.token_usage.to_dict(),
                )
                ctx.state.completed_stages.add(stage.name)
            elif result.status == StageStatus.FAILED:
                # 写入 stage.failed 事件
                self.writer.emit(
                    "stage.failed",
                    self.run_dir.name,
                    stage=stage.name,
                    error=result.error,
                    duration_ms=duration_ms,
                )
                ctx.state.failed_stages.add(stage.name)
            
            return result
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 写入 stage.failed 事件
            self.writer.emit(
                "stage.failed",
                self.run_dir.name,
                stage=stage.name,
                error=str(e),
                duration_ms=duration_ms,
            )
            ctx.state.failed_stages.add(stage.name)
            
            return StageResult(
                status=StageStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def _stub_handler(self, ctx: StageContext, stage: Stage) -> StageResult:
        """Stub 阶段处理器（用于测试）"""
        outputs = []
        
        for output_name in stage.outputs:
            # 创建 stub 输出
            content = {
                "stage": stage.name,
                "run_id": ctx.run_id,
                "requirement": ctx.requirement,
                "inputs": list(ctx.inputs.keys()),
                "stub": True,
            }
            
            ref = ctx.store.write(output_name, content)
            outputs.append(ref)
            
            # 写入 artifact.written 事件
            ctx.writer.emit(
                "artifact.written",
                ctx.run_id,
                artifact=ref.to_dict(),
            )
            
            # 更新状态
            ctx.state.artifacts[output_name] = ref
        
        return StageResult(
            status=StageStatus.COMPLETED,
            outputs=outputs,
        )


# ========== 便捷函数 ==========

def run_workflow(
    run_dir: Path,
    requirement: str = "",
    resume: bool = False,
    from_stage: str = None,
    fail_fast: bool = False,
    stages: List[Stage] = None,
) -> RunState:
    """
    运行工作流
    
    Args:
        run_dir: Run 目录
        requirement: 需求描述
        resume: 是否恢复
        from_stage: 从指定阶段开始
        fail_fast: 失败时立即终止
        stages: 自定义阶段列表
        
    Returns:
        最终状态
    """
    machine = StageMachine(run_dir, stages=stages, fail_fast=fail_fast)
    return machine.run(requirement, resume, from_stage)


def get_run_status(run_dir: Path) -> RunState:
    """获取 run 状态"""
    reconstructor = StateReconstructor(run_dir)
    return reconstructor.reconstruct()
