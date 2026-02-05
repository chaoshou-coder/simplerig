"""
SimpleRig - 多 Agent 工作流框架
改进版，解决所有硬编码问题
"""
from .config import Config, get_config, reload_config
from .planner import Planner, AtomicTask
from .lint_guard import LintGuard, LintResult
from .events import (
    Event,
    ArtifactRef,
    EventWriter,
    EventReader,
    ArtifactStore,
    RunLock,
    create_run_context,
)
from .runner import (
    Stage,
    StageStatus,
    StageResult,
    StageContext,
    StageMachine,
    RunState,
    StateReconstructor,
    run_workflow,
    get_run_status,
)
from .scheduler import (
    Task,
    TaskStatus,
    TaskResult,
    TaskGraph,
    TaskExecutor,
    StubExecutor,
    ParallelScheduler,
    create_parallel_tasks,
    run_parallel_tasks,
)
from .stages import (
    plan_handler,
    develop_handler,
    verify_handler,
    integrate_handler,
    get_default_stages,
)
from .stats import (
    TokenUsage,
    StageStats,
    TaskStats,
    RunStats,
    StatsCollector,
    collect_stats,
    save_stats,
    format_duration,
)

__version__ = "0.1.0"
__all__ = [
    # Config
    "Config",
    "get_config",
    "reload_config",
    # Planner
    "Planner",
    "AtomicTask",
    # LintGuard
    "LintGuard",
    "LintResult",
    # Events
    "Event",
    "ArtifactRef",
    "EventWriter",
    "EventReader",
    "ArtifactStore",
    "RunLock",
    "create_run_context",
    # Runner
    "Stage",
    "StageStatus",
    "StageResult",
    "StageContext",
    "StageMachine",
    "RunState",
    "StateReconstructor",
    "run_workflow",
    "get_run_status",
    # Scheduler
    "Task",
    "TaskStatus",
    "TaskResult",
    "TaskGraph",
    "TaskExecutor",
    "StubExecutor",
    "ParallelScheduler",
    "create_parallel_tasks",
    "run_parallel_tasks",
    # Stages
    "plan_handler",
    "develop_handler",
    "verify_handler",
    "integrate_handler",
    "get_default_stages",
    # Stats
    "TokenUsage",
    "StageStats",
    "TaskStats",
    "RunStats",
    "StatsCollector",
    "collect_stats",
    "save_stats",
    "format_duration",
]
