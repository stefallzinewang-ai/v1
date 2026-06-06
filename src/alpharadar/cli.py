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


def _cmd_sync_universe(args: argparse.Namespace) -> int:
    """采集一大批股票的历史行情（供规律挖掘/回测）。

    --board 指定板块代码（如 BK0457）只采该板块；否则采全 A 股（可 --limit 限量）。
    需在可访问东方财富的机器上运行。
    """
    from .config import Settings
    from .data.sources.eastmoney_source import EastmoneySource
    from .data.store import DataStore
    from .data.ingest import Ingestor

    settings = Settings.load()
    source = EastmoneySource(
        rate_limit_per_min=settings.get("data_source", "rate_limit_per_min", default=60),
        max_retries=settings.get("data_source", "max_retries", default=4))
    store = DataStore(root=settings.get("storage", "root", default="./data_store"))
    ing = Ingestor(source, store)
    start = settings.get("universe", "start", default="2010-01-01")
    end, indices = args.end, list(_default_indices().values())

    try:
        if args.board:
            uni = source.industry_members(args.board)["symbol"].tolist()
            print(f"板块 {args.board} 成分股 {len(uni)} 只")
        else:
            uni = source.stock_universe()["symbol"].tolist()
            print(f"全 A 股 {len(uni)} 只")
        if args.limit:
            uni = uni[:args.limit]
            print(f"限量至前 {len(uni)} 只")

        print("采集指数…")
        ing.sync_indices(indices, start, end)
        print(f"采集 {len(uni)} 只股票行情（{start} ~ {end}）…")
        total = 0
        for i in range(0, len(uni), 50):
            chunk = uni[i:i + 50]
            total += ing.sync_bars(chunk, start, end)
            print(f"  进度 {min(i + 50, len(uni))}/{len(uni)}（累计 {total} 行）")
        if args.with_financials:
            print("采集财务（供财务因子）…")
            n_fin = ing.sync_financials(uni, start, end)
            print(f"  财务写入 {n_fin} 行")
    except Exception as exc:
        print(f"\n采集失败：{type(exc).__name__}: {exc}")
        print("提示：云环境数据源会被拦截，请在本地运行。")
        return 1
    print(f"\n完成。可继续：python -m alpharadar.cli mine && ... backtest")
    return 0


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


def _cmd_demo(args: argparse.Namespace) -> int:
    """灌入合成演示数据，便于离线体验完整流程与界面。"""
    from .config import Settings
    from .data.store import DataStore
    from .demo import seed_demo_store

    settings = Settings.load()
    store = DataStore(root=settings.get("storage", "root", default="./data_store"))
    info = seed_demo_store(store)
    print(f"已灌入演示数据：{info['rows']} 行行情（指数 {info['indices']} + "
          f"候选 {info['candidates']} + 池 {info['universe']}），"
          f"财务 {info['financial_rows']} 行。")
    print("现在可以试：python -m alpharadar.cli run ai_optical_module")
    print("或打开界面：python -m alpharadar.cli ui")
    return 0


def _cmd_ui(args: argparse.Namespace) -> int:
    """启动图形界面（Streamlit）。"""
    import subprocess
    from pathlib import Path

    app = Path(__file__).resolve().parents[2] / "app.py"
    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("未安装 streamlit。请先：pip install streamlit")
        return 1
    print(f"启动界面：streamlit run {app}")
    return subprocess.call(["streamlit", "run", str(app),
                            "--server.port", str(args.port)])


def _cmd_mine(args: argparse.Namespace) -> int:
    """从本地行情训练「不同市场状态下的上涨规律」并保存规律库。

    需要先 sync 一批股票与指数的历史行情（越多越久越好）。
    """
    from pathlib import Path
    from .config import Settings
    from .data.store import DataStore
    from .mining.pattern_miner import PatternMiner

    settings = Settings.load()
    store = DataStore(root=settings.get("storage", "root", default="./data_store"))
    from .pipeline import build_panel_from_store
    built = build_panel_from_store(settings, store)
    if built is None:
        print("本地无行情。请先 sync 一批股票与指数的历史行情。")
        return 1
    print("构建训练面板…")
    panel, regimes, fwd = built
    if panel.empty:
        print("历史不足以构建训练面板（需更长的行情）。")
        return 1

    print(f"训练中（调仓点 {regimes.shape[0]}，观测 {fwd.shape[0]}）…")
    lib = PatternMiner(forward_days=settings.get("horizon", "forward_days", default=63)).fit(
        panel, regimes, fwd)
    path = Path(store.root) / "patterns.json"
    lib.save(path)

    print(f"\n已学得 {len(lib.patterns)} 个市场状态的规律 → {path}\n")
    print(f"{'市场状态':<24}{'样本内IC':>10}{'样本外IC':>10}{'观测':>8}")
    for rk, p in lib.patterns.items():
        oos = "—" if p.out_sample_ic is None else f"{p.out_sample_ic:>10.3f}"
        print(f"{rk:<24}{p.in_sample_ic:>10.3f}{oos:>10}{p.n_obs:>8}")
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    """回测：用已训练规律（或默认动量）在历史上回放，统计超额/胜率/回撤。"""
    from pathlib import Path
    from .config import Settings
    from .data.store import DataStore
    from .backtest.engine import BacktestEngine
    from .mining.pattern_miner import PatternLibrary

    settings = Settings.load()
    store = DataStore(root=settings.get("storage", "root", default="./data_store"))
    from .pipeline import build_panel_from_store
    built = build_panel_from_store(settings, store)
    if built is None:
        print("本地无行情。请先 sync 或 demo。")
        return 1
    panel, regimes, fwd = built
    if panel.empty:
        print("历史不足以回测（需更长的行情）。")
        return 1

    lib_path = Path(store.root) / "patterns.json"
    lib = PatternLibrary.load(lib_path) if lib_path.exists() else None
    res = BacktestEngine(
        top_k=args.top_k,
        forward_days=settings.get("horizon", "forward_days", default=63),
    ).run(panel, regimes, fwd, pattern_lib=lib)

    print("规律来源：" + ("已训练规律库 patterns.json" if lib else "默认动量基线"))
    print(res.summary())
    if res.by_regime:
        print("\n分市场状态超额：")
        for rk, st in res.by_regime.items():
            print(f"  {rk:<24} 期数 {st['n']:>3}  平均超额 {st['excess_mean'] * 100:+.2f}%")
    if args.save and res.periods is not None:
        out = Path(settings.get("report", "output_dir", default="./reports/output"))
        out.mkdir(parents=True, exist_ok=True)
        path = out / "backtest_periods.csv"
        res.periods.to_csv(path)
        print(f"\n（每期明细已保存到 {path}）")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """端到端运行一条主线：市场状态→激活→候选→打分→选股→报告。"""
    from pathlib import Path
    from .config import Settings
    from .pipeline import run_pipeline

    settings = Settings.load()
    result = run_pipeline(args.theme_id, as_of=args.as_of, settings=settings)
    print(result.report)

    out_dir = Path(settings.get("report", "output_dir", default="./reports/output"))
    if args.save:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = (args.as_of or "latest").replace("-", "")
        path = out_dir / f"{args.theme_id}_{stamp}.md"
        path.write_text(result.report, encoding="utf-8")
        print(f"\n（报告已保存到 {path}）")
    return 0


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

    p_su = sub.add_parser("sync-universe", help="采集一大批股票行情（供挖掘/回测）")
    p_su.add_argument("--board", default=None, help="只采某板块代码（如 BK0457）")
    p_su.add_argument("--limit", type=int, default=None, help="限制采集数量")
    p_su.add_argument("--end", default="2025-12-31", help="采集截止 YYYY-MM-DD")
    p_su.add_argument("--with-financials", action="store_true",
                      help="同时采集财务（供财务因子，较慢）")
    p_su.set_defaults(func=_cmd_sync_universe)

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

    sub.add_parser("demo", help="灌入合成演示数据（离线体验全流程）").set_defaults(func=_cmd_demo)

    p_ui = sub.add_parser("ui", help="启动图形界面（Streamlit）")
    p_ui.add_argument("--port", type=int, default=8501, help="端口（默认 8501）")
    p_ui.set_defaults(func=_cmd_ui)

    p_mine = sub.add_parser("mine", help="从历史行情训练不同市场状态下的上涨规律")
    p_mine.set_defaults(func=_cmd_mine)

    p_bt = sub.add_parser("backtest", help="回测：历史回放统计超额/胜率/回撤")
    p_bt.add_argument("--top-k", type=int, default=5, help="每期持有股票数")
    p_bt.add_argument("--save", action="store_true", help="保存每期明细 CSV")
    p_bt.set_defaults(func=_cmd_backtest)

    p_run = sub.add_parser("run", help="端到端运行：市场状态→激活→选股→报告")
    p_run.add_argument("theme_id", help="主线 id，如 ai_optical_module")
    p_run.add_argument("--as-of", default=None, help="point-in-time 日期 YYYY-MM-DD")
    p_run.add_argument("--save", action="store_true", help="同时把报告保存到 reports/output")
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
