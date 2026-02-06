"""
SimpleRig CLI - 命令行入口
子命令：init/emit/run/status/tail/list/stats/help
"""
import argparse
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

# Windows 环境下强制 UTF-8，防止中文乱码
if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

from .config import get_config
from .events import EventWriter


def create_parser() -> argparse.ArgumentParser:
    """创建命令行解析器"""
    parser = argparse.ArgumentParser(
        prog="simplerig",
        description="SimpleRig - 多 Agent 工作流框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  simplerig init "实现用户认证功能"
  simplerig emit stage.completed --stage plan --run-id 20260205_120000_abc123
  simplerig emit llm.called --run-id 20260205_120000_abc123 --prompt-tokens 1200 --completion-tokens 340
  simplerig run "实现用户认证功能"
  simplerig run --resume abc123
  simplerig run --from-stage plan
  simplerig status --run-id abc123
  simplerig tail --run-id abc123 --follow
"""
    )
    
    parser.add_argument(
        "--version", "-V",
        action="version",
        version="%(prog)s 0.1.0"
    )
    
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # init 子命令
    init_parser = subparsers.add_parser("init", help="初始化新 run")
    init_parser.add_argument(
        "requirement",
        type=str,
        nargs="?",
        help="自然语言需求描述"
    )
    
    # emit 子命令
    emit_parser = subparsers.add_parser("emit", help="记录事件")
    emit_parser.add_argument(
        "event",
        type=str,
        help="事件类型 (如 run.started, stage.completed)"
    )
    emit_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="Run ID"
    )
    emit_parser.add_argument(
        "--stage",
        type=str,
        help="阶段名称 (stage.* 事件需要)"
    )
    emit_parser.add_argument(
        "--data",
        type=str,
        help="附加 JSON 数据 (必须为对象)"
    )
    emit_parser.add_argument(
        "--token-usage",
        type=str,
        help="Token 使用量 JSON（对象，含 prompt_tokens/completion_tokens/total_tokens）"
    )
    emit_parser.add_argument(
        "--prompt-tokens",
        type=int,
        help="输入 tokens"
    )
    emit_parser.add_argument(
        "--completion-tokens",
        type=int,
        help="输出 tokens"
    )
    emit_parser.add_argument(
        "--total-tokens",
        type=int,
        help="总 tokens"
    )
    
    # run 子命令
    run_parser = subparsers.add_parser("run", help="运行工作流")
    run_parser.add_argument(
        "requirement",
        type=str,
        nargs="?",
        help="自然语言需求描述"
    )
    run_parser.add_argument(
        "--resume",
        type=str,
        nargs="?",
        const="latest",
        help="从指定 run_id 恢复执行（默认最近一次）"
    )
    run_parser.add_argument(
        "--from-stage",
        type=str,
        choices=["plan", "develop", "verify", "integrate"],
        help="从指定阶段开始执行"
    )
    run_parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="任何任务失败立即终止"
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预演模式，不实际执行"
    )
    run_parser.add_argument(
        "--max-agents",
        type=int,
        default=None,
        help="并行 agent 数上限"
    )
    run_parser.add_argument(
        "--tdd",
        action="store_true",
        help="启用 TDD 模式（develop 阶段执行红绿循环）"
    )
    run_parser.add_argument(
        "--bdd",
        action="store_true",
        help="启用 BDD 模式（verify 阶段执行 .feature 文件）"
    )

    # bdd 子命令组
    bdd_parser = subparsers.add_parser("bdd", help="BDD 相关命令")
    bdd_sub = bdd_parser.add_subparsers(dest="bdd_command", help="bdd 子命令")
    bdd_gen = bdd_sub.add_parser("generate", help="从规格生成 .feature 文件")
    bdd_gen.add_argument("spec", type=str, help="规格 JSON 文件路径")
    bdd_gen.add_argument("-o", "--output-dir", type=str, default=".", help="输出目录")
    bdd_gen.add_argument("--run-id", type=str, help="Run ID（可选，用于事件）")
    bdd_run = bdd_sub.add_parser("run", help="运行 .feature 文件")
    bdd_run.add_argument("feature", type=str, help=".feature 文件路径")
    bdd_run.add_argument("--run-id", type=str, help="Run ID（可选）")
    bdd_run.add_argument("--report", type=str, choices=["text", "json", "html"], default="text", help="报告格式")

    # status 子命令
    status_parser = subparsers.add_parser("status", help="查看运行状态")
    status_parser.add_argument(
        "--run-id",
        type=str,
        help="指定 run_id（默认最近一次）"
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式"
    )
    status_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细信息"
    )
    
    # tail 子命令
    tail_parser = subparsers.add_parser("tail", help="查看事件流")
    tail_parser.add_argument(
        "--run-id",
        type=str,
        help="指定 run_id（默认最近一次）"
    )
    tail_parser.add_argument(
        "--follow", "-f",
        action="store_true",
        help="持续监听新事件"
    )
    tail_parser.add_argument(
        "--lines", "-n",
        type=int,
        default=20,
        help="显示最近 N 行（默认 20）"
    )
    tail_parser.add_argument(
        "--filter",
        type=str,
        help="事件类型过滤（如 task.*, stage.*）"
    )
    
    # list 子命令
    list_parser = subparsers.add_parser("list", help="列出历史运行")
    list_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="显示最近 N 次（默认 10）"
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式"
    )
    
    # stats 子命令
    stats_parser = subparsers.add_parser("stats", help="查看运行统计")
    stats_parser.add_argument(
        "--run-id",
        type=str,
        help="指定 run_id（默认最近一次）"
    )
    stats_parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式"
    )
    
    return parser


def get_runs_dir() -> Path:
    """获取 runs 目录"""
    return Path("simplerig_data/runs")


def generate_run_id() -> str:
    """生成 run_id"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{timestamp}_{short_uuid}"


def get_latest_run_id() -> Optional[str]:
    """获取最近的 run_id"""
    runs_dir = get_runs_dir()
    if not runs_dir.exists():
        return None
    
    # 按修改时间排序
    runs = sorted(
        [d for d in runs_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True
    )
    
    if runs:
        return runs[0].name
    return None


def _parse_event_data(data: Optional[str]) -> dict:
    """解析事件附加数据（JSON 对象）"""
    if not data:
        return {}
    
    import json
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"无效的 JSON 数据: {exc}") from exc
    
    if not isinstance(parsed, dict):
        raise ValueError("附加数据必须是 JSON 对象")
    
    return parsed


def _parse_token_usage(data: Optional[str]) -> dict:
    """解析 token_usage JSON（对象）"""
    if not data:
        return {}
    
    import json
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"无效的 token_usage JSON: {exc}") from exc
    
    if not isinstance(parsed, dict):
        raise ValueError("token_usage 必须是 JSON 对象")
    
    return parsed


def _merge_token_usage(base: dict, extra: dict) -> dict:
    """合并并校验 token_usage"""
    usage = dict(base or {})
    usage.update(extra or {})
    
    # 转换并校验数值
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key in usage and usage[key] is not None:
            try:
                usage[key] = int(usage[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} 必须为整数") from exc
            if usage[key] < 0:
                raise ValueError(f"{key} 不能为负数")
    
    # 自动补全 total_tokens
    if "total_tokens" not in usage:
        if "prompt_tokens" in usage or "completion_tokens" in usage:
            usage["total_tokens"] = int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))
    
    return usage


def cmd_init(args: argparse.Namespace) -> int:
    """执行 init 命令"""
    if not args.requirement:
        print("错误：请提供需求描述", file=sys.stderr)
        return 1
    
    run_id = generate_run_id()
    run_dir = get_runs_dir() / run_id
    
    # 创建 run 目录结构
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    (run_dir / "locks").mkdir(exist_ok=True)
    
    # 写入 run.started 事件
    writer = EventWriter(run_dir)
    writer.emit("run.started", run_id, requirement=args.requirement)
    
    print(f"run_id={run_id}")
    return 0


def cmd_emit(args: argparse.Namespace) -> int:
    """执行 emit 命令"""
    run_dir = get_runs_dir() / args.run_id
    if not run_dir.exists():
        print(f"错误：run_id '{args.run_id}' 不存在", file=sys.stderr)
        return 1
    
    try:
        data = _parse_event_data(args.data)
        token_usage_json = _parse_token_usage(args.token_usage)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    
    # 合并 token_usage（允许从 --data 与显式参数传入）
    token_usage_base = {}
    if "token_usage" in data:
        if not isinstance(data["token_usage"], dict):
            print("错误：token_usage 必须是 JSON 对象", file=sys.stderr)
            return 1
        token_usage_base = data.get("token_usage", {})
    
    token_usage_args = {
        "prompt_tokens": args.prompt_tokens,
        "completion_tokens": args.completion_tokens,
        "total_tokens": args.total_tokens,
    }
    token_usage_args = {k: v for k, v in token_usage_args.items() if v is not None}
    
    try:
        token_usage = _merge_token_usage(token_usage_base, token_usage_json)
        token_usage = _merge_token_usage(token_usage, token_usage_args)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    
    if token_usage:
        data["token_usage"] = token_usage
    
    if args.stage:
        data["stage"] = args.stage
    
    if args.event.startswith("stage.") and "stage" not in data:
        print("错误：stage.* 事件需要 --stage", file=sys.stderr)
        return 1
    
    if args.event == "run.completed" and "stats" not in data:
        from .stats import collect_stats
        
        # 先收集一次统计，用于写入 run.completed 事件
        run_stats = collect_stats(run_dir)
        stats_payload = {
            "total_duration_ms": run_stats.total_duration_ms,
            "total_token_usage": run_stats.total_token_usage.to_dict(),
            "stages": {k: v.to_dict() for k, v in run_stats.stages.items()},
        }
        if token_usage:
            stats_payload["total_token_usage"] = token_usage
        data["stats"] = stats_payload
    
    writer = EventWriter(run_dir)
    writer.emit(args.event, args.run_id, **data)
    
    print(f"Event recorded: {args.event}")
    
    if args.event in ("run.completed", "run.failed", "run.aborted"):
        from .stats import collect_stats, save_stats
        
        run_stats = collect_stats(run_dir)
        save_stats(run_dir, run_stats)
        print(run_stats.summary())
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """执行 run 命令"""
    from .runner import StageMachine
    from .stages import get_default_stages
    
    config = get_config()
    
    # 确定 run_id
    if args.resume:
        if args.resume == "latest":
            run_id = get_latest_run_id()
            if not run_id:
                print("错误：没有找到可恢复的 run", file=sys.stderr)
                return 1
        else:
            run_id = args.resume
        
        run_dir = get_runs_dir() / run_id
        if not run_dir.exists():
            print(f"错误：run_id '{run_id}' 不存在", file=sys.stderr)
            return 1
        
        print(f"恢复执行: {run_id}")
        if args.from_stage:
            print(f"从阶段: {args.from_stage}")
    else:
        if not args.requirement:
            print("错误：请提供需求描述或使用 --resume", file=sys.stderr)
            return 1
        
        run_id = generate_run_id()
        print(f"新建 run: {run_id}")
        print(f"需求: {args.requirement}")
    
    # 创建 run 目录
    run_dir = get_runs_dir() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    (run_dir / "locks").mkdir(exist_ok=True)
    
    # 显示配置
    max_agents = args.max_agents or config.parallel.get("default_agents", 3)
    print(f"并行上限: {max_agents}")
    print(f"失败策略: {'fail-fast' if args.fail_fast else 'continue'}")
    
    print(f"\n运行目录: {run_dir}")
    print("事件日志: events.jsonl")
    print("产物目录: artifacts/")
    
    if args.dry_run:
        print("\n[预演模式]")
        print("预演完成，未实际执行")
        return 0
    
    # 执行阶段机（--tdd/--bdd 时使用增强阶段并传参）
    try:
        from .stats import collect_stats
        from .stages import get_enhanced_stages

        use_enhanced = getattr(args, "tdd", False) or getattr(args, "bdd", False)
        stages = get_enhanced_stages() if use_enhanced else get_default_stages()
        machine = StageMachine(run_dir, stages=stages, fail_fast=args.fail_fast)

        state = machine.run(
            requirement=args.requirement or "",
            resume=bool(args.resume),
            from_stage=args.from_stage,
            tdd=getattr(args, "tdd", False),
            bdd=getattr(args, "bdd", False),
        )
        
        print("\n执行完成")
        print(f"状态: {state.status}")
        print(f"完成阶段: {', '.join(state.completed_stages)}")
        if state.skipped_stages:
            print(f"跳过阶段: {', '.join(state.skipped_stages)}")
        if state.failed_stages:
            print(f"失败阶段: {', '.join(state.failed_stages)}")
        
        # 显示统计信息
        run_stats = collect_stats(run_dir)
        print(f"\n{run_stats.summary()}")
        
        return 0 if state.status == "completed" else 1
        
    except Exception as e:
        print(f"执行失败: {e}", file=sys.stderr)
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """执行 status 命令"""
    run_id = args.run_id or get_latest_run_id()
    
    if not run_id:
        print("未找到任何运行记录", file=sys.stderr)
        return 1
    
    run_dir = get_runs_dir() / run_id
    if not run_dir.exists():
        print("运行不存在", file=sys.stderr)
        return 1
    
    events_file = run_dir / "events.jsonl"
    artifacts_dir = run_dir / "artifacts"
    
    # 基本状态
    status_info = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "events_file": str(events_file),
        "events_exists": events_file.exists(),
        "artifacts_count": len(list(artifacts_dir.glob("*"))) if artifacts_dir.exists() else 0,
    }
    
    if args.json:
        import json
        print(json.dumps(status_info, indent=2, ensure_ascii=False))
    else:
        print(f"Run ID: {status_info['run_id']}")
        print(f"目录: {status_info['run_dir']}")
        print(f"事件日志: {'存在' if status_info['events_exists'] else '不存在'}")
        print(f"产物数量: {status_info['artifacts_count']}")
        
        if args.verbose and events_file.exists():
            print("\n最近事件:")
            # TODO: 解析 events.jsonl 显示详细状态
            print("  [待实现]")
    
    return 0


def cmd_tail(args: argparse.Namespace) -> int:
    """执行 tail 命令"""
    run_id = args.run_id or get_latest_run_id()
    
    if not run_id:
        print("未找到任何运行记录", file=sys.stderr)
        return 1
    
    run_dir = get_runs_dir() / run_id
    events_file = run_dir / "events.jsonl"
    
    if not events_file.exists():
        print(f"事件日志不存在: {events_file}", file=sys.stderr)
        return 1
    
    print(f"=== {run_id} 事件流 ===")
    
    if args.follow:
        print("[持续监听模式，Ctrl+C 退出]")
        # TODO: 实现 follow 模式
        print("[待实现]")
    else:
        # 读取最后 N 行
        lines = events_file.read_text(encoding="utf-8").strip().split("\n")
        tail_lines = lines[-args.lines:] if len(lines) > args.lines else lines
        
        for line in tail_lines:
            if args.filter:
                # 简单过滤
                import json
                try:
                    event = json.loads(line)
                    if not event.get("type", "").startswith(args.filter.replace("*", "")):
                        continue
                except json.JSONDecodeError:
                    pass
            print(line)
    
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """执行 list 命令"""
    runs_dir = get_runs_dir()
    
    if not runs_dir.exists():
        print("没有历史运行记录")
        return 0
    
    # 获取所有 run 目录
    runs = sorted(
        [d for d in runs_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True
    )[:args.limit]
    
    if not runs:
        print("没有历史运行记录")
        return 0
    
    if args.json:
        import json
        result = [
            {
                "run_id": d.name,
                "path": str(d),
                "mtime": d.stat().st_mtime,
            }
            for d in runs
        ]
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"最近 {len(runs)} 次运行:")
        for d in runs:
            mtime = datetime.fromtimestamp(d.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            events_file = d / "events.jsonl"
            status = "有事件" if events_file.exists() else "空"
            print(f"  {d.name}  [{status}]  {mtime}")
    
    return 0


def cmd_bdd(args: argparse.Namespace) -> int:
    """执行 bdd 子命令：generate / run"""
    if getattr(args, "bdd_command", None) == "generate":
        return cmd_bdd_generate(args)
    if getattr(args, "bdd_command", None) == "run":
        return cmd_bdd_run(args)
    print("请使用 bdd generate 或 bdd run", file=sys.stderr)
    return 1


def cmd_bdd_generate(args: argparse.Namespace) -> int:
    """bdd generate <spec.json> [-o output_dir] [--run-id]"""
    import json
    from pathlib import Path
    from .events import EventWriter
    from .bdd import BDDGenerator

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"文件不存在: {spec_path}", file=sys.stderr)
        return 1
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    output_dir = Path(args.output_dir)
    run_id = getattr(args, "run_id", None) or "cli"
    runs_dir = get_runs_dir()
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    writer = EventWriter(run_dir)
    gen = BDDGenerator(writer, run_id)
    path = gen.generate_from_spec(spec, output_dir)
    print(f"Generated: {path}")
    return 0


def cmd_bdd_run(args: argparse.Namespace) -> int:
    """bdd run <path.feature> [--run-id] [--report text|json|html]"""
    from pathlib import Path
    from .config import get_config
    from .events import EventWriter, ArtifactStore
    from .bdd import BDDRunner

    feature_path = Path(args.feature)
    if not feature_path.exists():
        print(f"文件不存在: {feature_path}", file=sys.stderr)
        return 1
    run_id = getattr(args, "run_id", None) or "cli"
    report_fmt = getattr(args, "report", "text") or "text"
    config = get_config()
    runs_dir = get_runs_dir()
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    writer = EventWriter(run_dir)
    store = ArtifactStore(run_dir)
    runner = BDDRunner(config, writer, run_id, store=store)
    result = runner.run_feature(feature_path)
    out = runner.generate_report(result, report_fmt, store=store)
    print(out)
    return 0 if result.passed else 1


def cmd_stats(args: argparse.Namespace) -> int:
    """执行 stats 命令"""
    from .stats import collect_stats
    
    run_id = args.run_id or get_latest_run_id()
    
    if not run_id:
        print("未找到任何运行记录", file=sys.stderr)
        return 1
    
    run_dir = get_runs_dir() / run_id
    if not run_dir.exists():
        print("运行不存在", file=sys.stderr)
        return 1
    
    # 收集统计
    stats = collect_stats(run_dir)
    
    if args.json:
        import json
        print(json.dumps(stats.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(stats.summary())
    
    return 0


def main(argv: list[str] = None) -> int:
    """CLI 主入口"""
    parser = create_parser()
    args = parser.parse_args(argv)
    
    if not args.command:
        parser.print_help()
        return 0
    
    # 分发到子命令
    commands = {
        "init": cmd_init,
        "emit": cmd_emit,
        "run": cmd_run,
        "bdd": cmd_bdd,
        "status": cmd_status,
        "tail": cmd_tail,
        "list": cmd_list,
        "stats": cmd_stats,
    }
    
    handler = commands.get(args.command)
    if handler:
        try:
            return handler(args)
        except KeyboardInterrupt:
            print("\n中断")
            return 130
        except Exception as e:
            print(f"错误: {e}", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
