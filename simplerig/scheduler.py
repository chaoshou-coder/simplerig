"""
Scheduler - 任务级并行调度器

核心组件：
- Task: 任务定义
- TaskGraph: 任务依赖图 (DAG)
- ParallelScheduler: 并行调度器
- StubExecutor: 测试用 stub 执行器
"""
import enum
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
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


# ========== 任务定义 ==========

class TaskStatus(enum.Enum):
    """任务状态"""
    PENDING = "pending"
    READY = "ready"      # 依赖满足，等待调度
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """任务定义"""
    id: str
    name: str
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    parallel_group: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 运行时状态
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    output: Optional[ArtifactRef] = None
    error: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    status: TaskStatus
    output: Optional[ArtifactRef] = None
    error: Optional[str] = None
    duration_ms: int = 0


# ========== 任务图 ==========

class TaskGraph:
    """
    任务依赖图 (DAG)
    
    支持：
    - 依赖检测
    - 就绪任务查询
    - 拓扑排序
    """
    
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self._lock = Lock()
    
    def add_task(self, task: Task):
        """添加任务"""
        with self._lock:
            self.tasks[task.id] = task
    
    def add_tasks(self, tasks: List[Task]):
        """批量添加任务"""
        for task in tasks:
            self.add_task(task)
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self.tasks.get(task_id)
    
    def get_ready_tasks(self) -> List[Task]:
        """
        获取就绪任务（依赖已满足）
        """
        with self._lock:
            ready = []
            for task in self.tasks.values():
                if task.status != TaskStatus.PENDING:
                    continue
                
                # 检查依赖是否都完成
                deps_satisfied = all(
                    self.tasks.get(dep_id) and 
                    self.tasks[dep_id].status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
                    for dep_id in task.dependencies
                )
                
                if deps_satisfied:
                    ready.append(task)
            
            return ready
    
    def mark_running(self, task_id: str):
        """标记任务为运行中"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.RUNNING
                self.tasks[task_id].start_time = datetime.now(timezone.utc).isoformat()
    
    def mark_completed(self, task_id: str, output: ArtifactRef = None):
        """标记任务为已完成"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.COMPLETED
                self.tasks[task_id].output = output
                self.tasks[task_id].end_time = datetime.now(timezone.utc).isoformat()
    
    def mark_failed(self, task_id: str, error: str):
        """标记任务为失败"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.FAILED
                self.tasks[task_id].error = error
                self.tasks[task_id].end_time = datetime.now(timezone.utc).isoformat()
    
    def mark_skipped(self, task_id: str):
        """标记任务为跳过"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.SKIPPED
    
    def mark_cancelled(self, task_id: str):
        """标记任务为取消"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.CANCELLED
    
    def is_all_done(self) -> bool:
        """检查是否所有任务都已完成"""
        with self._lock:
            return all(
                task.status in (
                    TaskStatus.COMPLETED, 
                    TaskStatus.FAILED, 
                    TaskStatus.SKIPPED,
                    TaskStatus.CANCELLED,
                )
                for task in self.tasks.values()
            )
    
    def get_statistics(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._lock:
            stats = {status.value: 0 for status in TaskStatus}
            for task in self.tasks.values():
                stats[task.status.value] += 1
            stats["total"] = len(self.tasks)
            return stats
    
    def can_retry(self, task_id: str) -> bool:
        """检查任务是否可以重试"""
        task = self.tasks.get(task_id)
        if not task:
            return False
        return task.retry_count < task.max_retries
    
    def increment_retry(self, task_id: str):
        """增加重试计数"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].retry_count += 1
                self.tasks[task_id].status = TaskStatus.PENDING


# ========== 执行器接口 ==========

class TaskExecutor:
    """任务执行器基类"""
    
    def execute(
        self,
        task: Task,
        context: Dict[str, Any],
    ) -> TaskResult:
        """
        执行任务
        
        Args:
            task: 任务
            context: 执行上下文
            
        Returns:
            执行结果
        """
        raise NotImplementedError


class StubExecutor(TaskExecutor):
    """
    Stub 执行器 - 用于测试
    
    特性：
    - 确定性输出
    - 可注入失败
    - 模拟延迟
    """
    
    def __init__(
        self,
        artifact_store: ArtifactStore,
        fail_tasks: Set[str] = None,
        delay_ms: int = 0,
    ):
        self.store = artifact_store
        self.fail_tasks = fail_tasks or set()
        self.delay_ms = delay_ms
    
    def execute(
        self,
        task: Task,
        context: Dict[str, Any],
    ) -> TaskResult:
        """执行 stub 任务"""
        start_time = time.time()
        
        # 模拟延迟
        if self.delay_ms > 0:
            time.sleep(self.delay_ms / 1000)
        
        # 检查是否注入失败
        if task.id in self.fail_tasks:
            duration_ms = int((time.time() - start_time) * 1000)
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error=f"Injected failure for task {task.id}",
                duration_ms=duration_ms,
            )
        
        # 创建 stub 输出
        output_content = {
            "task_id": task.id,
            "task_name": task.name,
            "description": task.description,
            "dependencies": task.dependencies,
            "parallel_group": task.parallel_group,
            "metadata": task.metadata,
            "context": {k: str(v) for k, v in context.items()},
            "stub": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        output_name = f"task_{task.id}.result.json"
        output_ref = self.store.write(output_name, output_content)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        return TaskResult(
            task_id=task.id,
            status=TaskStatus.COMPLETED,
            output=output_ref,
            duration_ms=duration_ms,
        )


# ========== 并行调度器 ==========

class ParallelScheduler:
    """
    并行调度器
    
    特性：
    - DAG 依赖就绪调度
    - 并发上限控制
    - 失败隔离（默认 non-fail-fast）
    - 可重试
    """
    
    def __init__(
        self,
        run_dir: Path,
        executor: TaskExecutor = None,
        max_workers: int = None,
        fail_fast: bool = False,
    ):
        self.run_dir = Path(run_dir)
        self.writer, self.store, self.lock = create_run_context(run_dir)
        
        # 执行器
        self.executor = executor or StubExecutor(self.store)
        
        # 并发配置
        config = get_config()
        self.max_workers = max_workers or config.parallel.get("max_agents", 5)
        self.fail_fast = fail_fast
        
        # 任务图
        self.graph = TaskGraph()
        
        # 调度状态
        self._should_stop = False
        self._lock = Lock()
    
    def load_plan(self, plan_path: str) -> List[Task]:
        """
        从计划文件加载任务
        
        Args:
            plan_path: 计划文件路径（相对于 artifacts）
            
        Returns:
            任务列表
        """
        plan_data = self.store.read_json(plan_path)
        tasks = []
        
        for task_data in plan_data.get("tasks", []):
            task = Task(
                id=task_data["id"],
                name=task_data.get("name", task_data["id"]),
                description=task_data.get("description", ""),
                dependencies=task_data.get("dependencies", []),
                parallel_group=task_data.get("parallel_group", 0),
                metadata=task_data.get("metadata", {}),
            )
            tasks.append(task)
        
        return tasks
    
    def schedule(
        self,
        tasks: List[Task],
        context: Dict[str, Any] = None,
    ) -> Dict[str, TaskResult]:
        """
        调度执行任务
        
        Args:
            tasks: 任务列表
            context: 执行上下文
            
        Returns:
            task_id -> TaskResult 映射
        """
        context = context or {}
        results: Dict[str, TaskResult] = {}
        
        # 添加任务到图
        self.graph.add_tasks(tasks)
        
        # 写入 task.created 事件
        for task in tasks:
            self.writer.emit(
                "task.created",
                self.run_dir.name,
                task_id=task.id,
                name=task.name,
                dependencies=task.dependencies,
                parallel_group=task.parallel_group,
            )
        
        # 使用线程池执行
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures: Dict[Future, str] = {}
            
            while not self.graph.is_all_done() and not self._should_stop:
                # 获取就绪任务
                ready_tasks = self.graph.get_ready_tasks()
                
                # 提交就绪任务
                for task in ready_tasks:
                    if len(futures) >= self.max_workers:
                        break
                    
                    self.graph.mark_running(task.id)
                    
                    # 写入 task.started 事件
                    self.writer.emit(
                        "task.started",
                        self.run_dir.name,
                        task_id=task.id,
                    )
                    
                    future = pool.submit(self._execute_task, task, context)
                    futures[future] = task.id
                
                if not futures:
                    # 没有运行中的任务且没有就绪任务
                    if not ready_tasks:
                        break
                    continue
                
                # 等待任何一个任务完成
                done_futures = []
                for future in as_completed(futures.keys(), timeout=0.1):
                    done_futures.append(future)
                    break
                
                if not done_futures:
                    continue
                
                # 处理完成的任务
                for future in done_futures:
                    task_id = futures.pop(future)
                    
                    try:
                        result = future.result()
                    except Exception as e:
                        result = TaskResult(
                            task_id=task_id,
                            status=TaskStatus.FAILED,
                            error=str(e),
                        )
                    
                    results[task_id] = result
                    self._handle_result(result)
                    
                    # fail-fast 检查
                    if self.fail_fast and result.status == TaskStatus.FAILED:
                        self._should_stop = True
                        # 取消其他任务
                        for f, tid in futures.items():
                            f.cancel()
                            self.graph.mark_cancelled(tid)
                        break
            
            # 等待剩余任务完成
            for future, task_id in futures.items():
                try:
                    result = future.result(timeout=60)
                except Exception as e:
                    result = TaskResult(
                        task_id=task_id,
                        status=TaskStatus.FAILED,
                        error=str(e),
                    )
                
                results[task_id] = result
                self._handle_result(result)
        
        return results
    
    def _execute_task(self, task: Task, context: Dict[str, Any]) -> TaskResult:
        """执行单个任务"""
        return self.executor.execute(task, context)
    
    def _handle_result(self, result: TaskResult):
        """处理任务结果"""
        task = self.graph.get_task(result.task_id)
        
        if result.status == TaskStatus.COMPLETED:
            self.graph.mark_completed(result.task_id, result.output)
            
            # 写入 task.completed 事件
            self.writer.emit(
                "task.completed",
                self.run_dir.name,
                task_id=result.task_id,
                output=result.output.to_dict() if result.output else None,
                duration_ms=result.duration_ms,
            )
            
            # 写入 artifact.written 事件
            if result.output:
                self.writer.emit(
                    "artifact.written",
                    self.run_dir.name,
                    artifact=result.output.to_dict(),
                )
        
        elif result.status == TaskStatus.FAILED:
            # 检查是否可以重试
            if self.graph.can_retry(result.task_id):
                self.graph.increment_retry(result.task_id)
                
                # 写入重试事件
                self.writer.emit(
                    "task.retrying",
                    self.run_dir.name,
                    task_id=result.task_id,
                    retry_count=task.retry_count if task else 0,
                    error=result.error,
                )
            else:
                self.graph.mark_failed(result.task_id, result.error)
                
                # 写入 task.failed 事件
                self.writer.emit(
                    "task.failed",
                    self.run_dir.name,
                    task_id=result.task_id,
                    error=result.error,
                    duration_ms=result.duration_ms,
                )
    
    def get_statistics(self) -> Dict[str, int]:
        """获取调度统计"""
        return self.graph.get_statistics()


# ========== 便捷函数 ==========

def create_parallel_tasks(
    task_specs: List[Dict[str, Any]],
    default_parallel: bool = True,
) -> List[Task]:
    """
    从规格创建并行任务
    
    Args:
        task_specs: 任务规格列表
        default_parallel: 默认并行（无依赖）
        
    Returns:
        任务列表
    """
    tasks = []
    
    for i, spec in enumerate(task_specs):
        task = Task(
            id=spec.get("id", f"task_{i}"),
            name=spec.get("name", f"Task {i}"),
            description=spec.get("description", ""),
            dependencies=spec.get("dependencies", []),
            parallel_group=spec.get("parallel_group", i % 3),
            metadata=spec.get("metadata", {}),
            max_retries=spec.get("max_retries", 3),
        )
        tasks.append(task)
    
    return tasks


def run_parallel_tasks(
    run_dir: Path,
    tasks: List[Task],
    executor: TaskExecutor = None,
    max_workers: int = None,
    fail_fast: bool = False,
    context: Dict[str, Any] = None,
) -> Dict[str, TaskResult]:
    """
    运行并行任务
    
    Args:
        run_dir: Run 目录
        tasks: 任务列表
        executor: 执行器
        max_workers: 最大并发数
        fail_fast: 失败时立即停止
        context: 执行上下文
        
    Returns:
        task_id -> TaskResult 映射
    """
    scheduler = ParallelScheduler(
        run_dir,
        executor=executor,
        max_workers=max_workers,
        fail_fast=fail_fast,
    )
    
    return scheduler.schedule(tasks, context)
