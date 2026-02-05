"""
Config - 统一配置加载器
解决硬编码问题，所有配置从 config.yaml 读取
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    """模型配置"""
    context_limit: int
    performance_degradation_point: float
    optimal_context: int
    strengths: list
    # 可选字段
    cost_per_1k: float = 0.0
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    provider: str = "cursor"
    tier: str = "standard"
    max_output: int = 0
    
    @property
    def safe_limit(self) -> int:
        """安全上下文上限"""
        return int(self.context_limit * self.performance_degradation_point)


@dataclass
class Config:
    """SimpleRig 配置"""
    # 模型注册表
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    
    # 角色分配
    roles: Dict[str, str] = field(default_factory=dict)
    
    # API 配置
    api: Dict[str, Any] = field(default_factory=dict)
    
    # 路径配置
    paths: Dict[str, Path] = field(default_factory=dict)
    
    # 项目结构
    project: Dict[str, list] = field(default_factory=dict)
    
    # 工具链
    tools: Dict[str, Any] = field(default_factory=dict)
    
    # 超时配置
    timeouts: Dict[str, int] = field(default_factory=dict)
    
    # 并行配置
    parallel: Dict[str, int] = field(default_factory=dict)
    
    # 预算
    budget: Dict[str, float] = field(default_factory=dict)
    
    # 日志
    logging: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def load(cls, config_path: str = "config.yaml") -> "Config":
        """加载配置"""
        # 1. 查找配置文件
        path = cls._find_config(config_path)
        
        if not path:
            print(f"Warning: Config file not found: {config_path}")
            print("Using default configuration")
            return cls._default()
        
        # 2. 加载 YAML (使用 UTF-8 编码)
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        # 3. 解析配置
        return cls._parse(data)
    
    @classmethod
    def _find_config(cls, config_path: str) -> Optional[Path]:
        """查找配置文件"""
        # 检查给定路径
        path = Path(config_path)
        if path.exists():
            return path
        
        # 检查环境变量
        if env_path := os.getenv("SIMPLERIG_CONFIG"):
            path = Path(env_path)
            if path.exists():
                return path
        
        # 检查标准位置
        for location in [
            "./config.yaml",
            "./simplerig_data/config.yaml",
            os.path.expanduser("~/.config/simplerig/config.yaml"),
        ]:
            path = Path(location)
            if path.exists():
                return path
        
        return None
    
    @classmethod
    def _parse(cls, data: Dict) -> "Config":
        """解析配置数据"""
        # 解析模型注册表
        models = {}
        for name, info in data.get("models", {}).get("registry", {}).items():
            models[name] = ModelConfig(**info)
        
        # 解析路径（支持环境变量）
        paths = {}
        for key, value in data.get("paths", {}).items():
            # 展开环境变量
            if isinstance(value, str):
                value = os.path.expandvars(value)
                # 如果是相对路径，转为绝对路径
                path = Path(value)
                if not path.is_absolute():
                    path = Path.cwd() / path
                paths[key] = path
            else:
                paths[key] = value
        
        return cls(
            models=models,
            roles=data.get("models", {}).get("roles", {}),
            api=data.get("api", {}),
            paths=paths,
            project=data.get("project", {}),
            tools=data.get("tools", {}),
            timeouts=data.get("timeouts", {}),
            parallel=data.get("parallel", {}),
            budget=data.get("budget", {}),
            logging=data.get("logging", {}),
        )
    
    @classmethod
    def _default(cls) -> "Config":
        """默认配置"""
        return cls(
            models={
                "opencode/kimi-k2.5-free": ModelConfig(
                    context_limit=8000,
                    performance_degradation_point=0.70,
                    optimal_context=4000,
                    cost_per_1k=0.0,
                    strengths=["code_gen", "text_analysis"],
                ),
                "openai/gpt-5.2-codex": ModelConfig(
                    context_limit=128000,
                    performance_degradation_point=0.80,
                    optimal_context=64000,
                    cost_per_1k=0.002,
                    strengths=["complex_reasoning", "reliable"],
                ),
            },
            roles={
                "architect": "openai/gpt-5.2-codex",
                "planner": "openai/gpt-5.2-codex",
                "dev": "opencode/kimi-k2.5-free",
            },
            paths={
                "database": Path("./simplerig_data/memory.db"),
                "logs": Path("./simplerig_data/logs"),
            },
            project={
                "source_dirs": ["src"],
                "test_dirs": ["tests"],
            },
            tools={
                "linter": "ruff",
                "formatter": "black",
                "test_runner": "pytest",
            },
            timeouts={
                "tdd_max_retries": 3,
                "monitor_stall": 60,
            },
            parallel={
                "default_agents": 3,
                "task_groups": 3,
            },
        )
    
    def get_model(self, role: str) -> tuple[str, ModelConfig]:
        """获取角色对应的模型"""
        model_name = self.roles.get(role, "opencode/kimi-k2.5-free")
        config = self.models.get(model_name)
        if not config:
            # 动态创建默认配置
            config = ModelConfig(
                context_limit=8000,
                performance_degradation_point=0.70,
                optimal_context=4000,
                cost_per_1k=0.002,
                strengths=[],
            )
        return model_name, config
    
    def get_timeout(self, key: str, default: int = 60) -> int:
        """获取超时配置"""
        return self.timeouts.get(key, default)


# 全局配置实例
_config: Optional[Config] = None


def get_config() -> Config:
    """获取全局配置"""
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def reload_config():
    """重新加载配置"""
    global _config
    _config = Config.load()


# 使用示例
if __name__ == "__main__":
    config = get_config()
    
    print("Models:")
    for name, model in config.models.items():
        print(f"  {name}: limit={model.context_limit}, safe={model.safe_limit}")
    
    print("\nRoles:")
    for role, model in config.roles.items():
        print(f"  {role}: {model}")
    
    print("\nPaths:")
    for key, path in config.paths.items():
        print(f"  {key}: {path}")
    
    print("\nTools:")
    for key, tool in config.tools.items():
        print(f"  {key}: {tool}")
