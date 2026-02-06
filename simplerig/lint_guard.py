"""
Lint Guard - 改进版代码风格检查
关键改进：
1. 工具链可配置（linter/formatter/test_runner）
2. 项目结构可配置（source_dirs/test_dirs）
3. 更好的错误处理和报告
"""
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import get_config
from .events import EventWriter


@dataclass
class LintIssue:
    """Lint 问题"""
    file: str
    line: int
    code: str
    message: str
    fixable: bool


@dataclass
class LintResult:
    """Lint 检查结果"""
    success: bool
    issues: List[LintIssue]
    fixed_count: int
    command: str
    stdout: str
    stderr: str


@dataclass
class TestRunResult:
    """测试执行结果"""
    success: bool
    exit_code: int  # 0=passed, 1=failed, 5=no tests
    stdout: str
    stderr: str
    skipped: bool
    test_count: int
    passed_count: int
    failed_count: int


class LintGuard:
    """
    代码风格守卫 - 改进版
    
    关键改进：
    1. 从 config 读取工具链配置
    2. 支持自定义项目结构
    3. 更好的错误处理和报告
    """
    
    def __init__(
        self,
        project_root: str = ".",
        config=None,
        writer: Optional[EventWriter] = None,
        run_id: str = "",
    ):
        self.project_root = Path(project_root)
        self.config = config or get_config()
        self.writer = writer
        self.run_id = run_id
        
        # 从配置读取工具链
        self.linter = self.config.tools.get("linter", "ruff")
        self.formatter = self.config.tools.get("formatter", "black")
        self.test_runner = self.config.tools.get("test_runner", "pytest")
        
        self.linter_args = self.config.tools.get("linter_args", ["check", "--fix"])
        self.formatter_args = self.config.tools.get("formatter_args", [])
        self.test_runner_args = self.config.tools.get("test_runner_args", ["-v"])
        
        # 从配置读取项目结构
        self.source_dirs = self.config.project.get("source_dirs", ["src"])
        self.test_dirs = self.config.project.get("test_dirs", ["tests"])
        
        print("LintGuard initialized:")
        print(f"  Linter: {self.linter}")
        print(f"  Formatter: {self.formatter}")
        print(f"  Test runner: {self.test_runner}")
        print(f"  Source dirs: {self.source_dirs}")
        print(f"  Test dirs: {self.test_dirs}")

    def _emit(self, event_type: str, **data) -> None:
        """可选事件发射（未传 writer 则跳过）"""
        if not self.writer:
            return
        self.writer.emit(event_type, self.run_id, **data)
    
    def check_and_fix(self, files: List[str] = None) -> LintResult:
        """
        检查并自动修复代码风格问题
        
        流程：
        1. 运行 linter（自动修复）
        2. 运行 formatter
        3. 再次检查确保全部通过
        """
        target = files or self._get_default_targets()
        all_issues = []
        fixed_count = 0
        stdout_all = []
        stderr_all = []

        self._emit("lint.started", targets=target)
        
        # 1. 运行 linter
        linter_result = self._run_tool(
            self.linter,
            self.linter_args + target,
            fix=True
        )
        all_issues.extend(linter_result["issues"])
        fixed_count += linter_result["fixed"]
        stdout_all.append(linter_result["stdout"])
        stderr_all.append(linter_result["stderr"])
        
        # 2. 运行 formatter
        formatter_result = self._run_tool(
            self.formatter,
            self.formatter_args + target
        )
        if formatter_result["reformatted"]:
            fixed_count += formatter_result["reformatted"]
        stdout_all.append(formatter_result["stdout"])
        stderr_all.append(formatter_result["stderr"])
        
        # 3. 最终检查（不修复）
        final_result = self._run_tool(
            self.linter,
            ["check"] + target,
            fix=False
        )
        all_issues = final_result["issues"]  # 使用最终检查结果
        stdout_all.append(final_result["stdout"])
        stderr_all.append(final_result["stderr"])
        
        success = len(all_issues) == 0

        if success:
            self._emit(
                "lint.passed",
                fixed_count=fixed_count,
                issues_count=len(all_issues),
            )
        else:
            self._emit(
                "lint.failed",
                fixed_count=fixed_count,
                issues_count=len(all_issues),
            )
        
        return LintResult(
            success=success,
            issues=all_issues,
            fixed_count=fixed_count,
            command=f"{self.linter} + {self.formatter}",
            stdout="\n".join(stdout_all),
            stderr="\n".join(stderr_all)
        )
    
    def run_tests(self, test_files: List[str] = None) -> TestRunResult:
        """
        运行测试。使用 self.test_runner + self.test_runner_args。
        exit code 5 -> skipped=True, success=True。
        """
        targets = test_files or self._get_test_targets()
        cmd = [self.test_runner] + self.test_runner_args + targets
        timeout = self.config.get_timeout("tool", 300)

        self._emit("test.started", targets=targets)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=timeout,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            stderr = f"{self.test_runner} timed out after {timeout}s"
            stdout = ""
            exit_code = 124
        except FileNotFoundError:
            stderr = f"{self.test_runner} not found. Please install it."
            stdout = ""
            exit_code = 1

        test_count, passed_count, failed_count = self._parse_pytest_summary(stdout + stderr)
        skipped = exit_code == 5
        success = exit_code in (0, 5)

        if exit_code == 0:
            self._emit(
                "test.passed",
                exit_code=exit_code,
                passed_count=passed_count,
                failed_count=failed_count,
                test_count=test_count,
            )
        elif exit_code == 5:
            self._emit("test.skipped", exit_code=exit_code)
        else:
            self._emit(
                "test.failed",
                exit_code=exit_code,
                passed_count=passed_count,
                failed_count=failed_count,
                test_count=test_count,
            )

        return TestRunResult(
            success=success,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            skipped=skipped,
            test_count=test_count,
            passed_count=passed_count,
            failed_count=failed_count,
        )

    def full_check(self, files: List[str] = None) -> Dict:
        """完整检查（lint + tests）"""
        lint_result = self.check_and_fix(files)
        test_result = self.run_tests()
        return {
            "lint": lint_result,
            "tests": test_result,
            "overall_success": lint_result.success and test_result.success,
        }

    def _get_default_targets(self) -> List[str]:
        """获取默认检查目标"""
        targets = []
        
        # 检查 source_dirs 和 test_dirs 是否存在
        for dir_name in self.source_dirs + self.test_dirs:
            dir_path = self.project_root / dir_name
            if dir_path.exists():
                targets.append(dir_name)
        
        # 如果没有找到任何目录，使用当前目录
        if not targets:
            targets = ["."]
        
        return targets

    def _get_test_targets(self) -> List[str]:
        """获取测试目标（仅 test_dirs）"""
        targets = []
        for dir_name in self.test_dirs:
            dir_path = self.project_root / dir_name
            if dir_path.exists():
                targets.append(dir_name)
        if not targets:
            targets = ["."]
        return targets

    def _parse_pytest_summary(self, output: str) -> Tuple[int, int, int]:
        """解析 pytest 输出中的 passed/failed 统计"""
        passed = 0
        failed = 0
        for line in output.splitlines():
            if "passed" in line or "failed" in line or "error" in line:
                passed_match = re.search(r"(\d+)\s+passed", line)
                failed_match = re.search(r"(\d+)\s+failed", line)
                error_match = re.search(r"(\d+)\s+errors?", line)
                if passed_match:
                    passed = int(passed_match.group(1))
                if failed_match:
                    failed = int(failed_match.group(1))
                if error_match:
                    failed += int(error_match.group(1))
        return passed + failed, passed, failed
    
    def _run_tool(self, tool: str, args: List[str], fix: bool = False) -> Dict:
        """运行工具"""
        cmd = [tool] + args
        timeout = self.config.timeouts.get("tool", None)
        if timeout is not None and timeout <= 0:
            timeout = None
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=timeout
            )
            
            # 解析输出
            if tool == self.linter:
                issues = self._parse_linter_output(result.stdout + result.stderr)
                fixed = self._count_fixed(result.stderr if fix else "")
                return {
                    "issues": issues,
                    "fixed": fixed,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
            elif tool == self.formatter:
                reformatted = self._count_reformatted(result.stderr)
                return {
                    "reformatted": reformatted,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
            else:
                return {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
                
        except subprocess.TimeoutExpired:
            error_msg = f"{tool} timed out after {timeout}s"
            if tool == self.linter:
                return {
                    "issues": [LintIssue(
                        file="N/A",
                        line=0,
                        code=f"{tool.upper()}_TIMEOUT",
                        message=error_msg,
                        fixable=False
                    )],
                    "fixed": 0,
                    "stdout": "",
                    "stderr": error_msg,
                    "returncode": 124
                }
            elif tool == self.formatter:
                return {
                    "reformatted": 0,
                    "stdout": "",
                    "stderr": error_msg,
                    "returncode": 124
                }
            return {
                "stdout": "",
                "stderr": error_msg,
                "returncode": 124
            }
        except FileNotFoundError:
            error_msg = f"{tool} not found. Please install it."
            return {
                "issues": [LintIssue(
                    file="N/A",
                    line=0,
                    code=f"{tool.upper()}_NOT_FOUND",
                    message=error_msg,
                    fixable=False
                )],
                "fixed": 0,
                "stdout": "",
                "stderr": error_msg,
                "returncode": 1
            }
    
    def _parse_linter_output(self, output: str) -> List[LintIssue]:
        """解析 linter 输出"""
        issues = []
        
        # 支持不同 linter 的输出格式
        if self.linter == "ruff":
            issues = self._parse_ruff_output(output)
        elif self.linter == "flake8":
            issues = self._parse_flake8_output(output)
        elif self.linter == "pylint":
            issues = self._parse_pylint_output(output)
        
        return issues
    
    def _parse_ruff_output(self, output: str) -> List[LintIssue]:
        """解析 ruff 输出"""
        issues = []
        
        for line in output.split('\n'):
            if ':' not in line:
                continue
            
            # ruff 格式: file.py:10:5: E501 Line too long
            parts = line.split(':', 3)
            if len(parts) < 4:
                continue
            
            try:
                file_path = parts[0]
                line_num = int(parts[1])
                code = parts[3].strip().split()[0]
                message = ' '.join(parts[3].strip().split()[1:])
                
                # 可自动修复的规则
                fixable = code.startswith(('F4', 'F5', 'I', 'UP'))
                
                issues.append(LintIssue(
                    file=file_path,
                    line=line_num,
                    code=code,
                    message=message,
                    fixable=fixable
                ))
            except Exception:
                continue
        
        return issues
    
    def _parse_flake8_output(self, output: str) -> List[LintIssue]:
        """解析 flake8 输出"""
        issues = []
        
        for line in output.split('\n'):
            if ':' not in line:
                continue
            
            # flake8 格式: file.py:10:5: E501 Line too long
            parts = line.split(':', 3)
            if len(parts) < 4:
                continue
            
            try:
                file_path = parts[0]
                line_num = int(parts[1])
                rest = parts[3].strip()
                code = rest.split()[0]
                message = ' '.join(rest.split()[1:])
                
                issues.append(LintIssue(
                    file=file_path,
                    line=line_num,
                    code=code,
                    message=message,
                    fixable=False  # flake8 不自动修复
                ))
            except Exception:
                continue
        
        return issues
    
    def _parse_pylint_output(self, output: str) -> List[LintIssue]:
        """解析 pylint 输出"""
        issues = []
        
        for line in output.split('\n'):
            # pylint 格式: file.py:10:5: C0301: Line too long (100/80)
            if ':' not in line:
                continue
            
            parts = line.split(':', 4)
            if len(parts) < 5:
                continue
            
            try:
                file_path = parts[0]
                line_num = int(parts[1])
                code = parts[3]
                message = parts[4]
                
                issues.append(LintIssue(
                    file=file_path,
                    line=line_num,
                    code=code,
                    message=message,
                    fixable=False
                ))
            except Exception:
                continue
        
        return issues
    
    def _count_fixed(self, stderr: str) -> int:
        """统计修复数量"""
        if "Fixed" in stderr:
            for line in stderr.split('\n'):
                if "Fixed" in line:
                    try:
                        return int(line.split()[1])
                    except Exception:
                        pass
        return 0
    
    def _count_reformatted(self, stderr: str) -> int:
        """统计格式化文件数"""
        if "reformatted" in stderr:
            for line in stderr.split('\n'):
                if "reformatted" in line:
                    try:
                        return int(line.split()[0])
                    except Exception:
                        pass
        return 0
    
    def must_pass(self, files: List[str] = None) -> Tuple[bool, str]:
        """
        必须通过的检查
        
        Returns:
            (success, report)
        """
        result = self.check_and_fix(files)
        
        if not result.success:
            report = f"""
❌ Lint check failed!
   Command: {result.command}
   Auto-fixed: {result.fixed_count} issues
   Remaining issues: {len(result.issues)}

   Issues:
"""
            for issue in result.issues[:5]:
                report += f"   - {issue.file}:{issue.line} {issue.code}: {issue.message}\n"
            
            if len(result.issues) > 5:
                report += f"   ... and {len(result.issues) - 5} more\n"
            
            return False, report
        
        report = f"✅ Lint check passed! (auto-fixed {result.fixed_count} issues)"
        return True, report


# 使用示例
if __name__ == "__main__":
    guard = LintGuard()
    
    success, report = guard.must_pass()
    print(report)
    
    if not success:
        sys.exit(1)
