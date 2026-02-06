"""
Planner - 改进版任务规划
关键改进：按执行模型的上下文要求拆分任务
"""
import re
from dataclasses import dataclass
from typing import List, Dict

from .config import get_config


@dataclass
class AtomicTask:
    """原子任务"""
    id: str
    description: str
    estimated_context: int
    dependencies: List[str]
    parallel_group: int
    assigned_model: str  # 新增：分配给哪个模型执行


class Planner:
    """
    任务规划器 - 改进版
    
    关键改进：
    1. 从 config 读取所有角色模型
    2. 按执行模型（dev）的上下文要求拆分任务
    3. 可配置的 task_groups
    """
    
    def __init__(self, config=None):
        self.config = config or get_config()
        
        # 获取规划模型（用于分析架构）
        self.planner_model_name, self.planner_config = self.config.get_model("planner")
        
        # 获取执行模型（用于决定拆分粒度）
        self.dev_model_name, self.dev_config = self.config.get_model("dev")
        
        # 使用执行模型的安全限制作为拆分依据
        self.safe_limit = self.dev_config.safe_limit
        
        # 可配置的并行组数
        self.task_groups = self.config.parallel.get("task_groups", 3)
        
        print("Planner initialized:")
        print(f"  Planner model: {self.planner_model_name}")
        print(f"  Dev model: {self.dev_model_name}")
        print(f"  Safe limit (for splitting): {self.safe_limit}")
        print(f"  Task groups: {self.task_groups}")
    
    def plan_from_architecture(self, architecture_doc: str) -> List[AtomicTask]:
        """
        从架构文档生成任务计划
        
        策略：
        1. 解析架构，识别模块
        2. 按执行模型（dev）的安全上下文限制拆分
        3. 识别并行关系
        """
        # 解析模块
        modules = self._parse_modules(architecture_doc)
        tasks = []
        
        for i, module in enumerate(modules):
            estimated = self._estimate_context(module)
            deps = self._detect_dependencies(module, modules, f"task_{i}", tasks)
            group = self._assign_group(deps, tasks)

            if estimated > self.safe_limit:
                sub_tasks = self._split_module(module, self.safe_limit, i)
                if sub_tasks:
                    sub_tasks[0].dependencies = deps
                    for t in sub_tasks:
                        t.parallel_group = group
                tasks.extend(sub_tasks)
            else:
                tasks.append(AtomicTask(
                    id=f"task_{i}",
                    description=module,
                    estimated_context=estimated,
                    dependencies=deps,
                    parallel_group=group,
                    assigned_model=self.dev_model_name,  # 明确分配给 dev 模型
                ))
        
        return tasks
    
    def _parse_modules(self, architecture: str) -> List[str]:
        """解析架构文档，提取模块"""
        lines = [line.strip() for line in architecture.split('\n') if line.strip()]
        return [line for line in lines if not line.startswith('#')]

    def _detect_dependencies(
        self,
        module: str,
        all_modules: List[str],
        task_id: str,
        existing_tasks: List[AtomicTask],
    ) -> List[str]:
        """
        识别模块依赖（简易关键词匹配）。
        """
        module_text = module.lower()
        deps = []

        def extract_keywords(text: str) -> List[str]:
            # 提取模块名与核心词
            if ":" in text:
                text = text.split(":", 1)[1]
            if "-" in text:
                text = text.split("-", 1)[0]
            tokens = re.split(r"[^a-zA-Z0-9_]+", text.lower())
            return [t for t in tokens if len(t) > 2]

        for task in existing_tasks:
            keywords = extract_keywords(task.description)
            if any(k in module_text for k in keywords):
                deps.append(task.id)

        # 去重并保持稳定顺序
        seen = set()
        ordered = []
        for dep in deps:
            if dep not in seen:
                seen.add(dep)
                ordered.append(dep)
        return ordered

    def _assign_group(self, deps: List[str], existing_tasks: List[AtomicTask]) -> int:
        """根据依赖的最大 group 值 +1 确定当前 group"""
        if not deps:
            return 0
        max_group = max(
            (t.parallel_group for t in existing_tasks if t.id in deps),
            default=0,
        )
        return max_group + 1
    
    def _estimate_context(self, module_desc: str) -> int:
        """
        估算模块上下文需求
        
        策略：按字符数估算 tokens（粗略：每4字符1 token）
        """
        chars = len(module_desc)
        tokens = chars // 4
        return min(tokens, self.dev_config.context_limit)
    
    def _split_module(self, module: str, limit: int, module_idx: int) -> List[AtomicTask]:
        """
        拆分大模块
        
        策略：按行数拆分为多个子任务
        """
        lines = module.split('\n')
        
        # 估算每行平均 tokens
        avg_tokens_per_line = len(module) // 4 // len(lines)
        lines_per_task = max(1, limit // avg_tokens_per_line)
        
        tasks = []
        for i in range(0, len(lines), lines_per_task):
            chunk = lines[i:i + lines_per_task]
            task_id = f"task_{module_idx}_{i // lines_per_task}"
            
            tasks.append(AtomicTask(
                id=task_id,
                description='\n'.join(chunk),
                estimated_context=limit // 2,  # 保守估计
                dependencies=[tasks[-1].id] if tasks else [],
                parallel_group=i // lines_per_task % self.task_groups,
                assigned_model=self.dev_model_name,
            ))
        
        return tasks
    
    def export_plan(self, tasks: List[AtomicTask]) -> Dict:
        """导出执行计划"""
        group_ids = sorted(set(t.parallel_group for t in tasks))
        return {
            "planner_model": self.planner_model_name,
            "dev_model": self.dev_model_name,
            "safe_context_limit": self.safe_limit,
            "total_tasks": len(tasks),
            "parallel_groups": [
                [t.id for t in tasks if t.parallel_group == g]
                for g in group_ids
            ],
            "parallel_group_count": len(group_ids),
            "dag_edges": {
                t.id: t.dependencies for t in tasks if t.dependencies
            },
            "tasks": [
                {
                    "id": t.id,
                    "description": t.description[:100] + "..." if len(t.description) > 100 else t.description,
                    "estimated_context": t.estimated_context,
                    "dependencies": t.dependencies,
                    "parallel_group": t.parallel_group,
                    "assigned_model": t.assigned_model,
                }
                for t in tasks
            ]
        }


# 使用示例
if __name__ == "__main__":
    planner = Planner()
    
    arch = """
# 视频知识提取器架构
Module 1: SRT Parser - 解析字幕文件，处理时间戳和文本合并
Module 2: Text Cleaner - 清理文本，删除语气词和重复强调
Module 3: Knowledge Extractor - 使用 LLM 提取结构化知识点
Module 4: Clustering - 跨文档主题聚类，构建课程结构
Module 5: Export - 导出 Markdown/HTML/EPUB 格式
"""
    
    tasks = planner.plan_from_architecture(arch)
    plan = planner.export_plan(tasks)
    
    print(f"\nGenerated {plan['total_tasks']} tasks")
    print(f"Dev model: {plan['dev_model']}")
    print(f"Safe limit: {plan['safe_context_limit']}")
    print(f"Parallel groups: {plan['parallel_groups']}")
    
    for t in plan['tasks']:
        print(f"  {t['id']}: {t['description'][:50]}...")
        print(f"    -> assigned to: {t['assigned_model']}")
