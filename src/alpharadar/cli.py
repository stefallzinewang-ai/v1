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


def _cmd_sync(args: argparse.Namespace) -> int:
    """采集某条主线候选股的行情与财务到本地存储（真实联网）。

    在云环境里数据源被网络策略拦截会报错；请在能访问东方财富的机器上运行。
    """
    from .config import Settings, ThemeConfig
    from .data.sources.eastmoney_source import EastmoneySource
    from .data.store import DataStore
    from .data.ingest import Ingestor

    settings = Settings.load()
    theme = ThemeConfig.load(args.theme_id)
    symbols = theme.seed_symbols
    if not symbols:
        print(f"主线 '{args.theme_id}' 没有候选种子股。")
        return 1

    source = EastmoneySource(
        rate_limit_per_min=settings.get("data_source", "rate_limit_per_min", default=60),
        max_retries=settings.get("data_source", "max_retries", default=4),
    )
    store = DataStore(root=settings.get("storage", "root", default="./data_store"))
    ing = Ingestor(source, store)
    start = settings.get("universe", "start", default="2010-01-01")
    end = args.end

    indices = list((settings.get("regime", "indices", default=None) or
                    _default_indices()).values())

    print(f"采集主线 '{theme.name}' 候选股：{', '.join(symbols)}")
    print(f"区间：{start} ~ {end}\n")
    try:
        n_idx = ing.sync_indices(indices, start, end)
        print(f"  指数：写入 {n_idx} 行（用于市场状态）")
        n_bars = ing.sync_bars(symbols, start, end)
        print(f"  行情：写入 {n_bars} 行")
        n_fin = ing.sync_financials(symbols, start, end)
        print(f"  财务：写入 {n_fin} 行")
    except Exception as exc:  # 网络被拦截等
        print(f"\n采集失败：{type(exc).__name__}: {exc}")
        print("提示：若在云环境，金融数据源可能被网络策略拦截；请在本地运行。")
        return 1
    print(f"\n完成。数据已落地到 {store.root}")
    return 0


def _default_indices() -> dict:
    from .regime.detector import DEFAULT_INDICES

    return DEFAULT_INDICES


def _cmd_regime(args: argparse.Namespace) -> int:
    """读取本地已采集的指数行情，判断并打印当前市场状态。"""
    from .config import Settings
    from .data.store import DataStore
    from .regime.detector import RegimeDetector

    settings = Settings.load()
    store = DataStore(root=settings.get("storage", "root", default="./data_store"))
    indices_map = settings.get("regime", "indices", default=None) or _default_indices()
    bars = store.read_bars(symbols=list(indices_map.values()))
    if bars.empty:
        print("本地没有指数行情。请先运行：python -m alpharadar.cli sync <theme>")
        return 1

    detector = RegimeDetector(
        trend_ma_window=settings.get("regime", "trend_ma_window", default=200),
        smoothing_days=settings.get("regime", "smoothing_days", default=5),
        indices=indices_map,
    )
    state = detector.detect(bars, as_of=args.as_of)
    print(f"市场状态 @ {state.as_of}")
    print(f"  趋势 trend          : {state.trend}")
    print(f"  风格 style          : {state.style}")
    print(f"  风险偏好 risk        : {state.risk_appetite}")
    print(f"  流动性 liquidity     : {state.liquidity}")
    print(f"  状态键 key           : {state.key()}")
    return 0


def _cmd_theme(args: argparse.Namespace) -> int:
    """展示某条主线的收敛链：结构 → 对当前市场状态的激活判断 → 候选股池。"""
    from .config import Settings
    from .data.store import DataStore
    from .theme import ThemeEngine

    settings = Settings.load()
    store = DataStore(root=settings.get("storage", "root", default="./data_store"))
    eng = ThemeEngine.from_id(args.theme_id)

    print(f"主线：{eng.theme.name}")
    bn = eng.bottleneck()
    if bn:
        print(f"瓶颈环节：{bn.get('name')} —— {bn.get('note', '')}")
    print("关键变量：")
    for v in eng.key_variables():
        print(f"  · {v.get('name')}（{v.get('metric')}）")

    # 对当前市场状态判断激活（景气因子未就绪 → None）
    indices_map = settings.get("regime", "indices", default=None) or _default_indices()
    bars = store.read_bars(symbols=list(indices_map.values()))
    print("\n激活判断：")
    if bars.empty:
        print("  （本地无指数行情，先 sync 才能判断市场状态）")
    else:
        from .regime.detector import RegimeDetector

        regime = RegimeDetector(
            trend_ma_window=settings.get("regime", "trend_ma_window", default=200),
            smoothing_days=settings.get("regime", "smoothing_days", default=5),
            indices=indices_map,
        ).detect(bars, as_of=args.as_of)
        act = eng.evaluate(regime, industry_prosperity=args.prosperity)
        print(f"  市场状态：{regime.key()}  →  {'✅ 激活' if act.active else '⛔ 未激活'}")
        for r in act.reasons:
            print(f"    {r}")

    # 候选股池
    members = store.read_table("industry")
    pool = eng.resolve_pool(members if not members.empty else None)
    print(f"\n候选股池（{pool.note}）：")
    print(f"  {', '.join(pool.enriched)}")
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    """对某条主线候选池按基本面打分排序（读本地已采集的财务数据）。"""
    from .config import Settings
    from .data.store import DataStore
    from .theme import ThemeEngine
    from .fundamental.scorer import FundamentalScorer

    settings = Settings.load()
    store = DataStore(root=settings.get("storage", "root", default="./data_store"))
    eng = ThemeEngine.from_id(args.theme_id)

    fin = store.read_table("financials")
    if fin.empty:
        print("本地无财务数据。请先运行：python -m alpharadar.cli sync <theme>")
        return 1

    industry = store.read_table("industry")
    pool = set(eng.resolve_pool(industry if not industry.empty else None).enriched)
    fin = fin[fin["symbol"].isin(pool)]

    scorer = FundamentalScorer(emphasis=eng.fundamental_emphasis())
    result = scorer.score(fin, as_of=args.as_of or "2025-12-31")
    if result.empty:
        print("候选池内无可用财务数据（可能公告日晚于 as-of）。")
        return 1

    print(f"主线 '{eng.theme.name}' 候选池基本面打分（as_of={args.as_of or '2025-12-31'}）：\n")
    print(f"{'代码':<12}{'报告期':<12}{'成长':>8}{'质量':>8}{'总分':>8}")
    for sym, row in result.iterrows():
        print(f"{sym:<12}{str(row['report_period']):<12}"
              f"{row['growth']:>8.2f}{row['quality']:>8.2f}{row['total']:>8.2f}")
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

    p_sync = sub.add_parser("sync", help="采集某条主线候选股的行情/财务到本地（联网）")
    p_sync.add_argument("theme_id", help="主线 id，如 ai_optical_module")
    p_sync.add_argument("--end", default="2025-12-31", help="采集截止日期 YYYY-MM-DD")
    p_sync.set_defaults(func=_cmd_sync)

    p_regime = sub.add_parser("regime", help="判断当前市场状态（需先 sync 指数行情）")
    p_regime.add_argument("--as-of", default=None, help="指定日期 YYYY-MM-DD（默认最新）")
    p_regime.set_defaults(func=_cmd_regime)

    p_theme = sub.add_parser("theme", help="展示主线收敛链：结构/激活判断/候选池")
    p_theme.add_argument("theme_id", help="主线 id，如 ai_optical_module")
    p_theme.add_argument("--as-of", default=None, help="指定日期 YYYY-MM-DD")
    p_theme.add_argument("--prosperity", type=float, default=None,
                         help="行业景气分位 0~1（阶段3前可手动传入测试）")
    p_theme.set_defaults(func=_cmd_theme)

    p_score = sub.add_parser("score", help="对主线候选池按基本面打分排序（需先 sync 财务）")
    p_score.add_argument("theme_id", help="主线 id，如 ai_optical_module")
    p_score.add_argument("--as-of", default=None, help="point-in-time 日期 YYYY-MM-DD")
    p_score.set_defaults(func=_cmd_score)

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
