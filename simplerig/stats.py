"""
Stats - 统计模块

统计功能：
- 总耗时
- 总 token 消耗
- 各阶段耗时
- 各阶段 token 消耗
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .events import EventReader, ArtifactStore


@dataclass
class TokenUsage:
    """Token 使用量"""
    prompt_tokens: int = 0      # 输入 tokens
    completion_tokens: int = 0  # 输出 tokens
    total_tokens: int = 0       # 总 tokens
    
    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )
    
    def to_dict(self) -> Dict[str, int]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenUsage":
        if not data:
            return cls()
        return cls(
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
        )


@dataclass
class StageStats:
    """阶段统计"""
    name: str
    status: str = "unknown"
    duration_ms: int = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "duration_formatted": format_duration(self.duration_ms),
            "token_usage": self.token_usage.to_dict(),
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


@dataclass 
class TaskStats:
    """任务统计"""
    task_id: str
    name: str = ""
    status: str = "unknown"
    duration_ms: int = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "duration_formatted": format_duration(self.duration_ms),
            "token_usage": self.token_usage.to_dict(),
        }


@dataclass
class RunStats:
    """Run 统计"""
    run_id: str
    status: str = "unknown"
    requirement: str = ""
    
    # 时间
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    total_duration_ms: int = 0
    
    # Token 统计
    total_token_usage: TokenUsage = field(default_factory=TokenUsage)
    token_recorded: bool = False
    
    # 阶段统计
    stages: Dict[str, StageStats] = field(default_factory=dict)
    
    # 任务统计
    tasks: Dict[str, TaskStats] = field(default_factory=dict)
    
    # 事件数
    event_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "requirement": self.requirement,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration_ms": self.total_duration_ms,
            "total_duration_formatted": format_duration(self.total_duration_ms),
            "total_token_usage": self.total_token_usage.to_dict(),
            "token_recorded": self.token_recorded,
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "event_count": self.event_count,
        }
    
    def summary(self) -> str:
        """生成可读摘要"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"Run 统计: {self.run_id}")
        lines.append("=" * 60)
        lines.append(f"状态: {self.status}")
        lines.append(f"需求: {self.requirement[:50]}..." if len(self.requirement) > 50 else f"需求: {self.requirement}")
        lines.append("")
        
        # 总体统计
        lines.append("【总体统计】")
        lines.append(f"  总耗时: {format_duration(self.total_duration_ms)}")
        if self.token_recorded:
            lines.append(f"  总 Token: {self.total_token_usage.total_tokens:,}")
            lines.append(f"    - 输入: {self.total_token_usage.prompt_tokens:,}")
            lines.append(f"    - 输出: {self.total_token_usage.completion_tokens:,}")
        else:
            lines.append("  总 Token: 未记录")
            lines.append("    - 需要记录 llm.called 或阶段/任务 token_usage")
        lines.append("")
        
        # 阶段统计
        if self.stages:
            lines.append("【阶段统计】")
            lines.append(f"  {'阶段':<12} {'状态':<10} {'耗时':<15} {'Token':>10}")
            lines.append("  " + "-" * 50)
            for name, stage in self.stages.items():
                token_cell = (
                    f"{stage.token_usage.total_tokens:>10,}"
                    if self.token_recorded
                    else f"{'-':>10}"
                )
                lines.append(
                    f"  {name:<12} {stage.status:<10} "
                    f"{format_duration(stage.duration_ms):<15} "
                    f"{token_cell}"
                )
            lines.append("")
        
        # 任务统计
        if self.tasks:
            lines.append("【任务统计】")
            lines.append(f"  {'任务ID':<20} {'状态':<10} {'耗时':<15} {'Token':>10}")
            lines.append("  " + "-" * 58)
            for task_id, task in self.tasks.items():
                token_cell = (
                    f"{task.token_usage.total_tokens:>10,}"
                    if self.token_recorded
                    else f"{'-':>10}"
                )
                lines.append(
                    f"  {task_id:<20} {task.status:<10} "
                    f"{format_duration(task.duration_ms):<15} "
                    f"{token_cell}"
                )
            lines.append("")
        
        lines.append("=" * 60)
        return "\n".join(lines)


def format_duration(ms: int) -> str:
    """格式化耗时"""
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms / 1000:.2f}s"
    elif ms < 3600000:
        minutes = ms // 60000
        seconds = (ms % 60000) / 1000
        return f"{minutes}m {seconds:.1f}s"
    else:
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        return f"{hours}h {minutes}m"


def parse_iso_timestamp(ts: str) -> Optional[datetime]:
    """解析 ISO 时间戳"""
    if not ts:
        return None
    try:
        # 处理带 Z 结尾的格式
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        return datetime.fromisoformat(ts)
    except:
        return None


def calculate_duration(start: str, end: str) -> int:
    """计算两个时间戳之间的毫秒数"""
    start_dt = parse_iso_timestamp(start)
    end_dt = parse_iso_timestamp(end)
    
    if start_dt and end_dt:
        delta = end_dt - start_dt
        return int(delta.total_seconds() * 1000)
    return 0


class StatsCollector:
    """统计收集器 - 从事件流收集统计信息"""
    
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.reader = EventReader(run_dir)
    
    def collect(self) -> RunStats:
        """收集统计信息"""
        stats = RunStats(run_id=self.run_dir.name)
        
        # 临时存储阶段开始时间
        stage_starts: Dict[str, str] = {}
        task_starts: Dict[str, str] = {}
        
        for event in self.reader.iter_events():
            stats.event_count += 1
            self._process_event(stats, event, stage_starts, task_starts)
        
        # 计算总耗时
        if stats.start_time and stats.end_time:
            stats.total_duration_ms = calculate_duration(stats.start_time, stats.end_time)
        
        # 如果没有结束时间，用最后事件时间估算
        if stats.start_time and not stats.end_time:
            last_event = self.reader.get_last_event()
            if last_event:
                stats.total_duration_ms = calculate_duration(stats.start_time, last_event.timestamp)
        
        return stats
    
    def _process_event(
        self, 
        stats: RunStats, 
        event, 
        stage_starts: Dict[str, str],
        task_starts: Dict[str, str],
    ):
        """处理单个事件"""
        
        # Run 事件
        if event.type == "run.started":
            stats.status = "running"
            stats.requirement = event.data.get("requirement", "")
            stats.start_time = event.timestamp
        
        elif event.type == "run.completed":
            stats.status = "completed"
            stats.end_time = event.timestamp
            # 提取统计摘要（如果有）
            if "stats" in event.data:
                self._merge_stats_from_event(stats, event.data["stats"])
        
        elif event.type == "run.failed":
            stats.status = "failed"
            stats.end_time = event.timestamp
        
        # Stage 事件
        elif event.type == "stage.started":
            stage_name = event.data.get("stage", "")
            stage_starts[stage_name] = event.timestamp
            
            if stage_name not in stats.stages:
                stats.stages[stage_name] = StageStats(name=stage_name)
            stats.stages[stage_name].start_time = event.timestamp
            stats.stages[stage_name].status = "running"
        
        elif event.type == "stage.completed":
            stage_name = event.data.get("stage", "")
            
            if stage_name not in stats.stages:
                stats.stages[stage_name] = StageStats(name=stage_name)
            
            stage_stats = stats.stages[stage_name]
            stage_stats.status = "completed"
            stage_stats.end_time = event.timestamp
            
            # 从事件数据获取耗时
            if "duration_ms" in event.data:
                stage_stats.duration_ms = event.data["duration_ms"]
            elif stage_name in stage_starts:
                stage_stats.duration_ms = calculate_duration(
                    stage_starts[stage_name], 
                    event.timestamp
                )
            
            # 从事件数据获取 token 使用量
            if "token_usage" in event.data:
                stage_stats.token_usage = TokenUsage.from_dict(event.data["token_usage"])
                stats.total_token_usage = stats.total_token_usage + stage_stats.token_usage
                stats.token_recorded = True
        
        elif event.type == "stage.failed":
            stage_name = event.data.get("stage", "")
            
            if stage_name not in stats.stages:
                stats.stages[stage_name] = StageStats(name=stage_name)
            
            stage_stats = stats.stages[stage_name]
            stage_stats.status = "failed"
            stage_stats.end_time = event.timestamp
            
            if "duration_ms" in event.data:
                stage_stats.duration_ms = event.data["duration_ms"]
        
        elif event.type == "stage.skipped":
            stage_name = event.data.get("stage", "")
            
            if stage_name not in stats.stages:
                stats.stages[stage_name] = StageStats(name=stage_name)
            
            stats.stages[stage_name].status = "skipped"
        
        # Task 事件
        elif event.type == "task.created":
            task_id = event.data.get("task_id", "")
            stats.tasks[task_id] = TaskStats(
                task_id=task_id,
                name=event.data.get("name", task_id),
                status="pending",
            )
        
        elif event.type == "task.started":
            task_id = event.data.get("task_id", "")
            task_starts[task_id] = event.timestamp
            
            if task_id in stats.tasks:
                stats.tasks[task_id].status = "running"
        
        elif event.type == "task.completed":
            task_id = event.data.get("task_id", "")
            
            if task_id in stats.tasks:
                task_stats = stats.tasks[task_id]
                task_stats.status = "completed"
                
                # 耗时
                if "duration_ms" in event.data:
                    task_stats.duration_ms = event.data["duration_ms"]
                elif task_id in task_starts:
                    task_stats.duration_ms = calculate_duration(
                        task_starts[task_id],
                        event.timestamp
                    )
                
                # Token 使用量
                if "token_usage" in event.data:
                    task_stats.token_usage = TokenUsage.from_dict(event.data["token_usage"])
                    stats.total_token_usage = stats.total_token_usage + task_stats.token_usage
                    stats.token_recorded = True
        
        elif event.type == "task.failed":
            task_id = event.data.get("task_id", "")
            
            if task_id in stats.tasks:
                stats.tasks[task_id].status = "failed"
                
                if "duration_ms" in event.data:
                    stats.tasks[task_id].duration_ms = event.data["duration_ms"]
        
        # LLM 调用事件（直接记录 token）
        elif event.type == "llm.called":
            token_usage = TokenUsage.from_dict(event.data.get("token_usage", {}))
            stats.total_token_usage = stats.total_token_usage + token_usage
            stats.token_recorded = True
    
    def _merge_stats_from_event(self, stats: RunStats, event_stats: Dict):
        """从事件中合并统计数据"""
        if "total_token_usage" in event_stats:
            # 使用事件中的统计（可能更准确）
            total = TokenUsage.from_dict(event_stats["total_token_usage"])
            stats.total_token_usage = total
            if total.total_tokens or total.prompt_tokens or total.completion_tokens:
                stats.token_recorded = True


def collect_stats(run_dir: Path) -> RunStats:
    """收集 run 统计"""
    collector = StatsCollector(run_dir)
    return collector.collect()


def save_stats(run_dir: Path, stats: RunStats):
    """保存统计到 artifacts"""
    store = ArtifactStore(run_dir)
    store.write("stats.json", stats.to_dict())
