"""
TDD Runner - 红绿循环

实现 Red -> Green -> Refactor 循环，通过 EventWriter 发射 tdd.* 事件，
复用 Config 超时与工具链、LintGuard 风格的子进程执行。
"""
import enum
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import Config
from .events import EventWriter


class TDDPhase(enum.Enum):
    """TDD 阶段"""
    RED = "red"
    GREEN = "green"
    REFACTOR = "refactor"


@dataclass
class TDDResult:
    """单次 TDD 循环结果"""
    success: bool
    red_passed: bool  # Red 阶段是否按预期失败
    green_passed: bool
    retries: int = 0
    red_output: str = ""
    green_output: str = ""
    error: Optional[str] = None
    phase: TDDPhase = TDDPhase.GREEN


class TDDRunner:
    """
    TDD 红绿循环执行器。

    从 config.timeouts 读取 tdd_red_phase / tdd_green_phase / tdd_max_retries，
    从 config.tools 读取 test_runner / test_runner_args。
    """

    def __init__(self, config: Config, writer: EventWriter, run_id: str):
        self.config = config
        self.writer = writer
        self.run_id = run_id
        self.red_timeout = config.get_timeout("tdd_red_phase", 30)
        self.green_timeout = config.get_timeout("tdd_green_phase", 30)
        self.max_retries = config.get_timeout("tdd_max_retries", 3)
        self.test_runner = config.tools.get("test_runner", "pytest")
        self.test_args = config.tools.get("test_runner_args", ["-v"])
        if isinstance(self.test_args, str):
            self.test_args = [self.test_args]

    def run_cycle(
        self,
        test_file: Path,
        impl_file: Path,
        dev_func: Callable[[], None],
        project_root: Optional[Path] = None,
    ) -> TDDResult:
        """
        执行一轮红 -> 绿循环，最多重试 max_retries 次。

        - Red: 运行测试，期望失败；若不失败则视为 red_failed。
        - 调用 dev_func() 生成/修改实现。
        - Green: 运行测试，期望通过；若不通过则重试（再次 dev_func + 运行）。
        """
        cwd = Path(project_root) if project_root else test_file.parent
        retries = 0

        self.writer.emit("tdd.red_started", self.run_id, test_file=str(test_file))

        red_ok, red_output = self._run_red(test_file, cwd)
        if not red_ok:
            self.writer.emit(
                "tdd.red_failed",
                self.run_id,
                test_file=str(test_file),
                output=red_output[:2000],
            )
            return TDDResult(
                success=False,
                red_passed=False,
                green_passed=False,
                red_output=red_output,
                error="Red phase failed: tests did not fail as expected",
            )
        self.writer.emit("tdd.red_passed", self.run_id, test_file=str(test_file))

        while retries <= self.max_retries:
            dev_func()
            self.writer.emit("tdd.green_started", self.run_id, test_file=str(test_file), retry=retries)

            green_ok, green_output = self._run_green(test_file, cwd)
            if green_ok:
                self.writer.emit(
                    "tdd.green_passed",
                    self.run_id,
                    test_file=str(test_file),
                    retries=retries,
                )
                self.writer.emit(
                    "tdd.cycle_completed",
                    self.run_id,
                    test_file=str(test_file),
                    retries=retries,
                )
                return TDDResult(
                    success=True,
                    red_passed=True,
                    green_passed=True,
                    retries=retries,
                    red_output=red_output,
                    green_output=green_output,
                )

            self.writer.emit(
                "tdd.green_failed",
                self.run_id,
                test_file=str(test_file),
                retry=retries,
                output=green_output[:2000],
            )
            retries += 1

        self.writer.emit(
            "tdd.cycle_failed",
            self.run_id,
            test_file=str(test_file),
            retries=retries,
            output=green_output[:2000],
        )
        return TDDResult(
            success=False,
            red_passed=True,
            green_passed=False,
            retries=retries,
            red_output=red_output,
            green_output=green_output,
            error=f"Green phase failed after {retries} retries",
        )

    def _run_red(self, test_file: Path, cwd: Path) -> tuple[bool, str]:
        """运行测试，期望失败 (returncode != 0)。返回 (是否符合预期, 输出)。"""
        cmd = [self.test_runner] + self.test_args + [str(test_file)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=self.red_timeout,
            )
            out = (result.stdout or "") + (result.stderr or "")
            # 期望失败：returncode != 0
            return (result.returncode != 0, out)
        except subprocess.TimeoutExpired:
            return (False, f"Timeout after {self.red_timeout}s")
        except FileNotFoundError:
            return (False, f"{self.test_runner} not found")

    def _run_green(self, test_file: Path, cwd: Path) -> tuple[bool, str]:
        """运行测试，期望通过 (returncode == 0)。返回 (是否通过, 输出)。"""
        cmd = [self.test_runner] + self.test_args + [str(test_file)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=self.green_timeout,
            )
            out = (result.stdout or "") + (result.stderr or "")
            return (result.returncode == 0, out)
        except subprocess.TimeoutExpired:
            return (False, f"Timeout after {self.green_timeout}s")
        except FileNotFoundError:
            return (False, f"{self.test_runner} not found")
