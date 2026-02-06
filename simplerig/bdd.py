"""
BDD - Feature/Scenario/Step 数据模型、Gherkin 生成与执行

- BDDGenerator: dict 规格 -> .feature 文件，发射 bdd.feature_generated
- BDDRunner: 解析 Gherkin、执行步骤、生成 text/json/html 报告，写入 ArtifactStore
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import Config
from .events import ArtifactStore, EventWriter


# ========== 数据模型 ==========


@dataclass
class Step:
    """Gherkin 步骤"""
    keyword: str  # Given / When / Then / And / But
    text: str
    line_number: int = 0


@dataclass
class Scenario:
    """场景"""
    name: str
    steps: List[Step] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class Feature:
    """Feature 文件模型"""
    name: str
    description: str = ""
    scenarios: List[Scenario] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    as_a: str = ""
    i_want: str = ""
    so_that: str = ""


# ========== BDDGenerator ==========


class BDDGenerator:
    """从 dict 规格生成 Gherkin .feature 文件"""

    def __init__(self, writer: EventWriter, run_id: str):
        self.writer = writer
        self.run_id = run_id

    def generate_from_spec(self, spec: Dict[str, Any], output_dir: Path) -> Path:
        """
        dict 规格 -> .feature 文件。
        支持 as_a / i_want / so_that 生成默认场景。
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        name = spec.get("name", "Unnamed Feature")
        description = spec.get("description", "")
        as_a = spec.get("as_a", "")
        i_want = spec.get("i_want", "")
        so_that = spec.get("so_that", "")
        tags = spec.get("tags", [])
        scenarios_data = spec.get("scenarios", [])

        if not scenarios_data and (as_a or i_want or so_that):
            scenarios_data = [
                {
                    "name": "Default scenario from user story",
                    "steps": [
                        {"keyword": "Given", "text": f"as a {as_a or 'user'}"},
                        {"keyword": "When", "text": i_want or "I perform the action"},
                        {"keyword": "Then", "text": so_that or "I get the outcome"},
                    ],
                }
            ]

        lines = []
        if tags:
            lines.append(" ".join(f"@{t}" for t in tags))
        lines.append(f"Feature: {name}")
        if description:
            for d in description.strip().split("\n"):
                lines.append(f"  {d}")
        if as_a or i_want or so_that:
            if as_a:
                lines.append(f"  As a {as_a}")
            if i_want:
                lines.append(f"  I want {i_want}")
            if so_that:
                lines.append(f"  So that {so_that}")
        lines.append("")

        for sc in scenarios_data:
            sc_tags = sc.get("tags", [])
            if sc_tags:
                lines.append("  " + " ".join(f"@{t}" for t in sc_tags))
            lines.append(f"  Scenario: {sc.get('name', 'Unnamed')}")
            for st in sc.get("steps", []):
                kw = st.get("keyword", "Given")
                text = st.get("text", "")
                lines.append(f"    {kw} {text}")
            lines.append("")

        safe_name = re.sub(r"[^\w\-]", "_", name).strip("_") or "feature"
        file_path = output_dir / f"{safe_name}.feature"
        file_path.write_text("\n".join(lines), encoding="utf-8")

        self.writer.emit(
            "bdd.feature_generated",
            self.run_id,
            path=str(file_path),
            feature=name,
        )
        return file_path

    def generate_batch(
        self, specs: List[Dict[str, Any]], output_dir: Path
    ) -> List[Path]:
        """批量生成 .feature 文件"""
        paths = []
        for spec in specs:
            paths.append(self.generate_from_spec(spec, output_dir))
        return paths


# ========== Gherkin 解析与执行 ==========


@dataclass
class StepResult:
    """单步执行结果"""
    step: Step
    passed: bool
    error: Optional[str] = None


@dataclass
class ScenarioResult:
    """场景执行结果"""
    scenario: Scenario
    steps: List[StepResult]
    passed: bool


@dataclass
class TestResult:
    """Feature 执行结果"""
    feature_path: str
    feature_name: str
    scenarios: List[ScenarioResult]
    passed: bool
    duration_ms: int = 0


def _parse_gherkin(content: str) -> Feature:
    """简易 Gherkin 解析：Feature、Scenario、Given/When/Then/And/But。"""
    lines = content.split("\n")
    feature = Feature(name="")
    current_scenario: Optional[Scenario] = None
    feature_tags: List[str] = []
    desc_lines: List[str] = []

    for i, raw in enumerate(lines):
        ln = i + 1
        line = raw.strip()
        if not line:
            continue
        if line.startswith("@"):
            tags = [t.strip() for t in line.split() if t.startswith("@")]
            if current_scenario is not None:
                current_scenario.tags = [t.lstrip("@") for t in tags]
            else:
                feature_tags = [t.lstrip("@") for t in tags]
        elif line.lower().startswith("feature:"):
            feature.name = line[8:].strip()
            feature.tags = feature_tags
        elif line.lower().startswith("scenario:"):
            if current_scenario is not None:
                feature.scenarios.append(current_scenario)
            current_scenario = Scenario(name=line[9:].strip())
        elif re.match(r"^(given|when|then|and|but)\s", line, re.I):
            if current_scenario is None:
                current_scenario = Scenario(name="(no name)")
            m = re.match(r"^(given|when|then|and|but)\s+(.*)$", line, re.I)
            if m:
                current_scenario.steps.append(
                    Step(keyword=m.group(1).capitalize(), text=m.group(2).strip(), line_number=ln)
                )
        elif current_scenario is None and feature.name and not line.lower().startswith("feature:"):
            if raw.startswith("  ") or raw.startswith("\t"):
                desc_lines.append(line)
    if current_scenario is not None:
        feature.scenarios.append(current_scenario)
    feature.description = "\n".join(desc_lines)
    return feature


class BDDRunner:
    """
    BDD 执行器：解析 .feature、执行步骤、生成报告。
    未注册的步骤默认通过（模拟）。
    """

    def __init__(
        self,
        config: Config,
        writer: EventWriter,
        run_id: str,
        store: Optional[ArtifactStore] = None,
    ):
        self.config = config
        self.writer = writer
        self.run_id = run_id
        self.store = store
        self._steps: Dict[str, Callable] = {}
        self._hooks: Dict[str, List[Callable]] = {}

    def register_step(self, pattern: str, func: Callable) -> None:
        """注册步骤。pattern 支持简单通配，如 'I have <n> apples' -> func(n)."""
        self._steps[pattern] = func

    def register_hook(self, hook_type: str, func: Callable) -> None:
        """注册钩子，如 before_feature, after_scenario。"""
        self._hooks.setdefault(hook_type, []).append(func)

    def _match_step(self, text: str) -> tuple[Optional[Callable], Optional[dict]]:
        """匹配步骤并提取参数。简单实现：精确匹配或首段匹配。"""
        for pattern, func in self._steps.items():
            if "<" in pattern:
                re_pat = re.escape(pattern)
                re_pat = re.sub(r"\\<([^>]+)\\>", r"(?P<\1>.+?)", re_pat)
                m = re.match(re_pat + "$", text.strip())
                if m:
                    return func, m.groupdict()
            elif pattern.strip() == text.strip():
                return func, {}
        return None, None

    def run_feature(self, feature_path: Path) -> TestResult:
        """解析并执行 .feature 文件，发射 bdd.* 事件。"""
        import time
        start = time.perf_counter()
        path = Path(feature_path)
        content = path.read_text(encoding="utf-8")
        feature = _parse_gherkin(content)

        self.writer.emit(
            "bdd.feature_started",
            self.run_id,
            path=str(path),
            feature=feature.name,
        )

        scenario_results: List[ScenarioResult] = []
        all_passed = True

        for sc in feature.scenarios:
            self.writer.emit(
                "bdd.scenario_started",
                self.run_id,
                scenario=sc.name,
            )
            step_results: List[StepResult] = []
            sc_passed = True
            for step in sc.steps:
                func, params = self._match_step(step.text)
                if func is not None:
                    try:
                        if params:
                            func(**params)
                        else:
                            func()
                        step_results.append(StepResult(step=step, passed=True))
                        self.writer.emit(
                            "bdd.step_passed",
                            self.run_id,
                            step=step.text,
                        )
                    except Exception as e:
                        step_results.append(StepResult(step=step, passed=False, error=str(e)))
                        self.writer.emit(
                            "bdd.step_failed",
                            self.run_id,
                            step=step.text,
                            error=str(e),
                        )
                        sc_passed = False
                else:
                    step_results.append(StepResult(step=step, passed=True))
                    self.writer.emit("bdd.step_passed", self.run_id, step=step.text)

            scenario_results.append(
                ScenarioResult(scenario=sc, steps=step_results, passed=sc_passed)
            )
            if not sc_passed:
                all_passed = False

        duration_ms = int((time.perf_counter() - start) * 1000)
        self.writer.emit(
            "bdd.feature_completed",
            self.run_id,
            path=str(path),
            feature=feature.name,
            passed=all_passed,
            duration_ms=duration_ms,
        )

        result = TestResult(
            feature_path=str(path),
            feature_name=feature.name,
            scenarios=scenario_results,
            passed=all_passed,
            duration_ms=duration_ms,
        )
        return result

    def generate_report(
        self,
        result: TestResult,
        format: str = "text",
        store: Optional[ArtifactStore] = None,
    ) -> str:
        """
        生成报告 (text / json / html)。
        若提供 store，将 json/html 写入 ArtifactStore (bdd_report.json, bdd_report.html)。
        """
        store = store or self.store
        if format == "json":
            data = {
                "feature_path": result.feature_path,
                "feature_name": result.feature_name,
                "passed": result.passed,
                "duration_ms": result.duration_ms,
                "scenarios": [
                    {
                        "name": sr.scenario.name,
                        "passed": sr.passed,
                        "steps": [
                            {"text": s.step.text, "passed": s.passed, "error": s.error}
                            for s in sr.steps
                        ],
                    }
                    for sr in result.scenarios
                ],
            }
            out = json.dumps(data, ensure_ascii=False, indent=2)
            if store:
                store.write("bdd_report.json", data)
            return out
        if format == "html":
            html = self._report_html(result)
            if store:
                store.write("bdd_report.html", html)
            return html
        return self._report_text(result)

    def _report_text(self, result: TestResult) -> str:
        lines = [
            f"Feature: {result.feature_name}",
            f"  Passed: {result.passed}",
            f"  Duration: {result.duration_ms} ms",
            "",
        ]
        for sr in result.scenarios:
            lines.append(f"  Scenario: {sr.scenario.name} ({'PASS' if sr.passed else 'FAIL'})")
            for s in sr.steps:
                lines.append(f"    {s.step.keyword} {s.step.text}: {'OK' if s.passed else s.error or 'FAIL'}")
        return "\n".join(lines)

    def _report_html(self, result: TestResult) -> str:
        status = "PASS" if result.passed else "FAIL"
        rows = []
        for sr in result.scenarios:
            for s in sr.steps:
                rows.append(
                    f"<tr><td>{sr.scenario.name}</td><td>{s.step.keyword} {s.step.text}</td>"
                    f"<td>{'PASS' if s.passed else 'FAIL'}</td><td>{s.error or '-'}</td></tr>"
                )
        table = "\n".join(rows)
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>BDD Report</title></head>
<body>
<h1>BDD Report: {result.feature_name}</h1>
<p>Status: <strong>{status}</strong> | Duration: {result.duration_ms} ms</p>
<table border="1"><tr><th>Scenario</th><th>Step</th><th>Result</th><th>Error</th></tr>
{table}
</table>
</body></html>"""
