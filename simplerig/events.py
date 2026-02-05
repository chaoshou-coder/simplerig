"""
事件系统 - JSONL 事件溯源基础设施

核心组件：
- Event: 事件数据模型
- EventWriter: 原子追加事件到 events.jsonl
- EventReader: 读取和重放事件流
- ArtifactStore: 写入 artifacts 并计算 sha256
- RunLock: run 级别的互斥锁
"""
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterator, List, Optional, Union

# 平台特定的文件锁定
if os.name == 'nt':
    import msvcrt
    fcntl = None  # Windows 没有 fcntl
else:
    import fcntl
    msvcrt = None  # Unix 没有 msvcrt


# ========== 事件数据模型 ==========

@dataclass
class Event:
    """事件基类"""
    type: str                       # 事件类型 (e.g., run.started, task.completed)
    timestamp: str                  # ISO 8601 时间戳
    seq: int = 0                    # 序列号（由 EventWriter 分配）
    run_id: str = ""                # 所属 run
    data: Dict[str, Any] = field(default_factory=dict)  # 事件数据
    
    @classmethod
    def create(cls, event_type: str, run_id: str = "", **data) -> "Event":
        """创建新事件（使用系统本地时区）"""
        return cls(
            type=event_type,
            timestamp=datetime.now().astimezone().isoformat(),
            run_id=run_id,
            data=data,
        )
    
    def to_json(self) -> str:
        """序列化为 JSON 行"""
        return json.dumps(asdict(self), ensure_ascii=False, separators=(',', ':'))
    
    @classmethod
    def from_json(cls, line: str) -> "Event":
        """从 JSON 行反序列化"""
        obj = json.loads(line)
        return cls(**obj)


@dataclass
class ArtifactRef:
    """产物引用"""
    ref: str            # 相对路径 (artifacts/xxx.json)
    sha256: str         # 内容哈希
    size: int           # 文件大小 (bytes)
    mime: str = "application/octet-stream"  # MIME 类型
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ========== 敏感信息脱敏 ==========

# 需要脱敏的 key 名称 (完整匹配，不区分大小写)
SENSITIVE_KEYS = {
    'api_key', 'apikey', 'api-key', 'api_token',
    'secret', 'secret_key', 'secretkey', 'secret_token',
    'password', 'passwd', 'pwd',
    'token', 'access_token', 'refresh_token', 'bearer_token', 'auth_token',
    'credential', 'credentials',
    'auth', 'auth_key', 'authorization',
    'private_key', 'privatekey',
}

# 不应被脱敏的 key (包含敏感词但实际是统计数据)
SAFE_KEYS = {
    'token_usage', 'prompt_tokens', 'completion_tokens', 'total_tokens',
    'token_count', 'tokens',
}


def sanitize_value(value: Any) -> Any:
    """脱敏单个值"""
    if isinstance(value, str):
        # 检查是否像 API key (长字符串，包含特定模式)
        if len(value) > 20 and any(c.isalnum() for c in value):
            # 可能是 key，检查上下文
            return value  # 这里保守处理，让调用方决定
        return value
    elif isinstance(value, dict):
        return sanitize_dict(value)
    elif isinstance(value, list):
        return [sanitize_value(v) for v in value]
    return value


def is_sensitive_key(key: str) -> bool:
    """检查 key 是否为敏感字段"""
    key_lower = key.lower()
    
    # 先检查是否在安全列表中
    if key_lower in SAFE_KEYS:
        return False
    
    # 检查是否在敏感列表中
    return key_lower in SENSITIVE_KEYS


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """脱敏字典中的敏感信息"""
    result = {}
    for key, value in data.items():
        # 检查 key 是否为敏感字段
        if is_sensitive_key(key):
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = sanitize_dict(value)
        elif isinstance(value, list):
            result[key] = [sanitize_value(v) for v in value]
        else:
            result[key] = value
    return result


def sanitize_event(event: Event) -> Event:
    """脱敏事件数据"""
    sanitized_data = sanitize_dict(event.data)
    return Event(
        type=event.type,
        timestamp=event.timestamp,
        seq=event.seq,
        run_id=event.run_id,
        data=sanitized_data,
    )


# ========== 文件锁 ==========

class FileLock:
    """跨平台文件锁"""
    
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._fd = None
    
    def acquire(self, blocking: bool = True, timeout: float = None) -> bool:
        """获取锁"""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            self._fd = open(self.lock_path, 'w')
            
            if os.name == 'nt':
                # Windows
                start = time.time()
                while True:
                    try:
                        msvcrt.locking(self._fd.fileno(), msvcrt.LK_NBLCK, 1)
                        return True
                    except IOError:
                        if not blocking:
                            return False
                        if timeout and (time.time() - start) >= timeout:
                            return False
                        time.sleep(0.1)
            else:
                # Unix
                flags = fcntl.LOCK_EX
                if not blocking:
                    flags |= fcntl.LOCK_NB
                try:
                    fcntl.flock(self._fd.fileno(), flags)
                    return True
                except BlockingIOError:
                    return False
        except Exception:
            if self._fd:
                self._fd.close()
                self._fd = None
            raise
    
    def release(self):
        """释放锁"""
        if self._fd:
            try:
                if os.name == 'nt':
                    msvcrt.locking(self._fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
            finally:
                self._fd.close()
                self._fd = None
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class RunLock:
    """Run 级别互斥锁"""
    
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.lock_path = self.run_dir / "locks" / "run.lock"
        self._lock = FileLock(self.lock_path)
    
    def acquire(self, blocking: bool = True, timeout: float = None) -> bool:
        """获取锁"""
        return self._lock.acquire(blocking, timeout)
    
    def release(self):
        """释放锁"""
        self._lock.release()
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


# ========== EventWriter ==========

class EventWriter:
    """
    事件写入器 - 原子追加事件到 events.jsonl
    
    特性：
    - 原子追加（单行 JSON）
    - 自动分配序列号
    - 自动脱敏敏感信息
    - 线程安全
    """
    
    def __init__(self, run_dir: Path, sanitize: bool = True):
        self.run_dir = Path(run_dir)
        self.events_file = self.run_dir / "events.jsonl"
        self.sanitize = sanitize
        self._seq = 0
        self._lock = Lock()
        
        # 初始化序列号（从现有文件恢复）
        self._init_seq()
    
    def _init_seq(self):
        """从现有文件初始化序列号"""
        if self.events_file.exists():
            with open(self.events_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            event = Event.from_json(line)
                            self._seq = max(self._seq, event.seq)
                        except:
                            pass
    
    def write(self, event: Event) -> Event:
        """
        写入事件
        
        Args:
            event: 要写入的事件
            
        Returns:
            写入后的事件（包含 seq）
        """
        with self._lock:
            # 分配序列号
            self._seq += 1
            event.seq = self._seq
            
            # 脱敏
            if self.sanitize:
                event = sanitize_event(event)
            
            # 确保目录存在
            self.events_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 原子追加
            with open(self.events_file, 'a', encoding='utf-8') as f:
                f.write(event.to_json() + '\n')
                f.flush()
                os.fsync(f.fileno())
            
            return event
    
    def emit(self, event_type: str, run_id: str = "", **data) -> Event:
        """
        便捷方法：创建并写入事件
        
        Args:
            event_type: 事件类型
            run_id: Run ID
            **data: 事件数据
            
        Returns:
            写入后的事件
        """
        event = Event.create(event_type, run_id, **data)
        return self.write(event)
    
    @property
    def current_seq(self) -> int:
        """当前序列号"""
        return self._seq


# ========== EventReader ==========

class EventReader:
    """
    事件读取器 - 读取和重放事件流
    """
    
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.events_file = self.run_dir / "events.jsonl"
    
    def read_all(self) -> List[Event]:
        """读取所有事件"""
        events = []
        if not self.events_file.exists():
            return events
        
        with open(self.events_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(Event.from_json(line))
                    except json.JSONDecodeError:
                        continue
        
        return events
    
    def iter_events(self) -> Iterator[Event]:
        """迭代读取事件"""
        if not self.events_file.exists():
            return
        
        with open(self.events_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield Event.from_json(line)
                    except json.JSONDecodeError:
                        continue
    
    def filter_by_type(self, type_prefix: str) -> List[Event]:
        """按类型前缀过滤事件"""
        return [e for e in self.read_all() if e.type.startswith(type_prefix)]
    
    def get_last_event(self, event_type: str = None) -> Optional[Event]:
        """获取最后一个事件（可选类型过滤）"""
        events = self.read_all()
        if event_type:
            events = [e for e in events if e.type == event_type]
        
        return events[-1] if events else None
    
    def tail(self, n: int = 20) -> List[Event]:
        """获取最后 N 个事件"""
        events = self.read_all()
        return events[-n:] if len(events) > n else events


# ========== ArtifactStore ==========

class ArtifactStore:
    """
    产物存储 - 写入 artifacts 并计算 sha256
    
    特性：
    - 自动计算 SHA256
    - 支持多种数据类型（str, bytes, dict）
    - 自动推断 MIME 类型
    """
    
    # MIME 类型映射
    MIME_TYPES = {
        '.json': 'application/json',
        '.jsonl': 'application/x-ndjson',
        '.txt': 'text/plain',
        '.md': 'text/markdown',
        '.py': 'text/x-python',
        '.yaml': 'application/x-yaml',
        '.yml': 'application/x-yaml',
        '.html': 'text/html',
        '.xml': 'application/xml',
        '.csv': 'text/csv',
    }
    
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.artifacts_dir = self.run_dir / "artifacts"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    def write(
        self,
        name: str,
        content: Union[str, bytes, dict, list],
        mime: str = None,
    ) -> ArtifactRef:
        """
        写入产物
        
        Args:
            name: 文件名 (e.g., plan.json, output.txt)
            content: 内容（str, bytes, 或可 JSON 序列化的对象）
            mime: MIME 类型（可选，自动推断）
            
        Returns:
            ArtifactRef 引用对象
        """
        artifact_path = self.artifacts_dir / name
        
        # 转换内容为 bytes
        if isinstance(content, dict) or isinstance(content, list):
            content_bytes = json.dumps(
                content, 
                ensure_ascii=False, 
                indent=2
            ).encode('utf-8')
            if mime is None:
                mime = 'application/json'
        elif isinstance(content, str):
            content_bytes = content.encode('utf-8')
        else:
            content_bytes = content
        
        # 计算 SHA256
        sha256 = hashlib.sha256(content_bytes).hexdigest()
        
        # 推断 MIME 类型
        if mime is None:
            ext = artifact_path.suffix.lower()
            mime = self.MIME_TYPES.get(ext, 'application/octet-stream')
        
        # 写入文件
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with open(artifact_path, 'wb') as f:
            f.write(content_bytes)
            f.flush()
            os.fsync(f.fileno())
        
        return ArtifactRef(
            ref=f"artifacts/{name}",
            sha256=sha256,
            size=len(content_bytes),
            mime=mime,
        )
    
    def read(self, name: str) -> bytes:
        """读取产物内容"""
        artifact_path = self.artifacts_dir / name
        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact not found: {name}")
        
        with open(artifact_path, 'rb') as f:
            return f.read()
    
    def read_json(self, name: str) -> Any:
        """读取 JSON 产物"""
        content = self.read(name)
        return json.loads(content.decode('utf-8'))
    
    def verify(self, ref: ArtifactRef) -> bool:
        """
        验证产物完整性
        
        Args:
            ref: 产物引用
            
        Returns:
            True 如果产物存在且 SHA256 匹配
        """
        name = ref.ref.replace("artifacts/", "")
        artifact_path = self.artifacts_dir / name
        
        if not artifact_path.exists():
            return False
        
        with open(artifact_path, 'rb') as f:
            content = f.read()
        
        actual_sha256 = hashlib.sha256(content).hexdigest()
        return actual_sha256 == ref.sha256 and len(content) == ref.size
    
    def list(self) -> List[str]:
        """列出所有产物"""
        if not self.artifacts_dir.exists():
            return []
        
        return [f.name for f in self.artifacts_dir.iterdir() if f.is_file()]
    
    def exists(self, name: str) -> bool:
        """检查产物是否存在"""
        return (self.artifacts_dir / name).exists()


# ========== 便捷函数 ==========

def create_run_context(run_dir: Path) -> tuple:
    """
    创建 run 上下文
    
    Returns:
        (EventWriter, ArtifactStore, RunLock)
    """
    run_dir = Path(run_dir)
    return (
        EventWriter(run_dir),
        ArtifactStore(run_dir),
        RunLock(run_dir),
    )
