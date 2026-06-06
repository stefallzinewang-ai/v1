"""命令行入口（骨架）。

先提供可运行的命令骨架：列出主线、查看主线详情、显示流水线步骤。
随着各层实现填充（见 docs/roadmap.md），run 子命令将端到端跑通。

用法：
    python -m alpharadar.cli --help
    python -m alpharadar.cli themes
    python -m alpharadar.cli show ai_optical_module
    python -m alpharadar.cli pipeline
"""
from __future__ import annotations

import argparse
import sys

from . import __version__


def _cmd_themes(_: argparse.Namespace) -> int:
    from .config import list_themes

    themes = list_themes()
    if not themes:
        print("未找到主线配置（config/themes/*.yaml）。")
        return 0
    print("可用主线：")
    for t in themes:
        print(f"  - {t}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    from .config import ThemeConfig

    theme = ThemeConfig.load(args.theme_id)
    print(f"主线：{theme.name}  (id={theme.id})")
    print(f"描述：{theme.raw.get('description', '').strip()}")
    bottleneck = theme.bottleneck_stage
    if bottleneck:
        print(f"瓶颈环节：{bottleneck.get('name')} —— {bottleneck.get('note', '')}")
    print(f"候选种子股：{', '.join(theme.seed_symbols) or '（无）'}")
    return 0


def _cmd_pipeline(_: argparse.Namespace) -> int:
    steps = [
        ("1 data", "采集行情/财务/宏观/行业（关联数据）"),
        ("2 regime", "识别当前市场状态（牛熊/风格/风险/流动性）"),
        ("3 mining", "调用按状态训练的因子规律 Pattern"),
        ("4 theme", "主题→瓶颈环节→候选股池"),
        ("5 fundamental", "公司各季度财务打分"),
        ("6 selection", "加权融合 → Top 1~2"),
        ("7 backtest", "历史回测验证（离线）"),
        ("8 report", "输出可追溯研究报告"),
    ]
    print("主线雷达 · 流水线（自上而下收敛）：")
    for name, desc in steps:
        print(f"  [{name:<14}] {desc}")
    print("\n注：当前为骨架阶段，各步实现进度见 docs/roadmap.md。")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    print(
        f"[run] 主线 '{args.theme_id}' 的端到端流水线尚未实现。\n"
        "      请按 docs/roadmap.md 依次填充各层（阶段 1 起）。"
    )
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpharadar",
        description="主线雷达 — 自上而下、市场状态感知的 A 股主题投资研究系统",
    )
    parser.add_argument("--version", action="version", version=f"alpharadar {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("themes", help="列出所有可用主线").set_defaults(func=_cmd_themes)

    p_show = sub.add_parser("show", help="查看某条主线的详情")
    p_show.add_argument("theme_id", help="主线 id，如 ai_optical_module")
    p_show.set_defaults(func=_cmd_show)

    sub.add_parser("pipeline", help="显示八层流水线步骤").set_defaults(func=_cmd_pipeline)

    p_run = sub.add_parser("run", help="对某条主线端到端运行（待实现）")
    p_run.add_argument("theme_id", help="主线 id")
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
