"""
SimpleRig - 多 Agent 工作流框架
改进版，解决所有硬编码问题
"""
from .config import Config, get_config, reload_config
from .planner import Planner, AtomicTask
from .lint_guard import LintGuard, LintResult

__version__ = "0.1.0"
__all__ = [
    "Config",
    "get_config",
    "reload_config",
    "Planner",
    "AtomicTask",
    "LintGuard",
    "LintResult",
]
