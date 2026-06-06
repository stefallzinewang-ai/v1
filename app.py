"""主线雷达 · 图形界面（Streamlit）

运行：
    streamlit run app.py
或：
    python -m alpharadar.cli ui

界面复用八层流水线（pipeline.run_pipeline），把「市场状态 → 主线激活 →
瓶颈环节 → 候选公司 → 研究报告」可视化呈现。

⚠️ 仅供研究与教育，不构成投资建议。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让脚本在未安装包时也能从 src 运行
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import streamlit as st  # noqa: E402

from alpharadar.config import Settings, list_themes  # noqa: E402
from alpharadar.data.store import DataStore  # noqa: E402
from alpharadar.pipeline import run_pipeline  # noqa: E402
from alpharadar.demo import seed_demo_store  # noqa: E402

st.set_page_config(page_title="主线雷达 · Mainline Alpha Radar",
                   page_icon="📡", layout="wide")


def _store(settings: Settings) -> DataStore:
    return DataStore(root=settings.get("storage", "root", default="./data_store"))


# ── 侧边栏：控制台 ────────────────────────────────────────────
st.sidebar.title("📡 主线雷达")
st.sidebar.caption("自上而下 · 市场状态感知的 A 股主题研究")

settings = Settings.load()
store = _store(settings)

themes = list_themes() or ["ai_optical_module"]
theme_id = st.sidebar.selectbox("选择主线", themes, index=0)
as_of = st.sidebar.text_input("分析时点 (YYYY-MM-DD)", value="2021-12-31")
top_n = st.sidebar.slider("候选数量 Top N", 1, 5, 2)

st.sidebar.divider()
has_data = not store.read_bars().empty
st.sidebar.write("**本地数据**：", "✅ 已就绪" if has_data else "⚠️ 暂无")

col_a, col_b = st.sidebar.columns(2)
if col_a.button("🎲 加载演示数据", width="stretch"):
    with st.spinner("正在生成合成演示数据…"):
        info = seed_demo_store(store)
    st.sidebar.success(f"已灌入 {info['rows']} 行行情")
    st.rerun()
if col_b.button("🗑️ 清空数据", width="stretch"):
    import shutil
    shutil.rmtree(store.root, ignore_errors=True)
    st.rerun()

st.sidebar.divider()
st.sidebar.caption(
    "真实数据：在可联网的机器上运行\n`python -m alpharadar.cli sync <主线>`\n"
    "（云环境数据源会被网络策略拦截）")


# ── 主区域 ────────────────────────────────────────────────────
st.title("研究面板")

if not has_data:
    st.info("👈 还没有数据。点左侧 **「加载演示数据」** 即可在离线环境体验完整流程；"
            "或在本地用 `sync` 采集真实行情。")
    st.stop()

settings_for_run = Settings(raw={**settings.raw,
                                 "selection": {**settings.get("selection", default={}), "top_n": top_n}})
with st.spinner("运行流水线中…"):
    result = run_pipeline(theme_id, as_of=as_of, settings=settings_for_run)

# 1) 市场状态
st.subheader("① 市场状态")
if result.regime is None:
    st.warning("缺指数行情，无法判断市场状态。")
else:
    r = result.regime
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("趋势 Trend", r.trend)
    c2.metric("风格 Style", r.style)
    c3.metric("风险偏好 Risk", r.risk_appetite)
    c4.metric("流动性 Liquidity", r.liquidity)
    st.caption(f"状态键：`{r.key()}`")

    # 市场状态历史时间线
    with st.expander("📈 市场状态历史时间线"):
        from alpharadar.regime.detector import RegimeDetector, DEFAULT_INDICES
        import pandas as _pd

        idx_map = settings.get("regime", "indices", default=None) or DEFAULT_INDICES
        idx_bars = store.read_bars(symbols=list(idx_map.values()))
        if not idx_bars.empty:
            hist = RegimeDetector(indices=idx_map).history(idx_bars, freq="ME")
            if not hist.empty:
                trend_num = {"bull": 1, "range": 0, "bear": -1}
                chart = _pd.DataFrame(
                    {"趋势(bull=1/bear=-1)": hist["trend"].map(trend_num).values},
                    index=_pd.to_datetime(hist["date"]))
                st.line_chart(chart)
                st.dataframe(hist[["date", "trend", "style", "risk_appetite"]],
                             width="stretch", hide_index=True)

# 2) 主线激活
st.subheader("② 主线激活判断")
if result.activation is None:
    st.warning("未做激活判断（缺市场状态）。")
else:
    if result.activation.active:
        st.success("✅ 主线已激活")
    else:
        st.error("⛔ 主线未激活")
    for reason in result.activation.reasons:
        st.write("　", reason)

# 3) 瓶颈环节
st.subheader("③ 产业链瓶颈环节")
from alpharadar.theme import ThemeEngine  # noqa: E402

eng = ThemeEngine.from_id(theme_id)
bn = eng.bottleneck()
if bn:
    st.markdown(f"**{bn.get('name')}** —— {bn.get('note', '')}")
kv = eng.key_variables()
if kv:
    st.table({"关键变量": [v.get("name") for v in kv],
              "观测指标": [v.get("metric") for v in kv]})

# 4) 候选公司
st.subheader(f"④ 候选公司（Top {len(result.candidates)}）")
if not result.candidates:
    st.warning("候选池内无可用数据（财务公告日可能晚于分析时点）。")
else:
    import pandas as pd

    rows = []
    for c in result.candidates:
        row = {"名称": c.name, "代码": c.symbol, "总分": round(c.total_score, 2),
               "报告期": c.report_period or "—"}
        row.update({k: round(v, 2) for k, v in c.breakdown.items()})
        rows.append(row)
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", hide_index=True)

    # 分项得分柱状图
    dim_cols = list(result.candidates[0].breakdown.keys())
    chart_df = pd.DataFrame(
        {c.name: c.breakdown for c in result.candidates}).T[dim_cols]
    st.bar_chart(chart_df)

    for c in result.candidates:
        with st.expander(f"💡 {c.name}（{c.symbol}）选中理由"):
            for reason in c.reasons:
                st.write("　", reason)

# 5) 完整报告
st.subheader("⑤ 研究报告")
with st.expander("查看 / 下载完整 Markdown 报告", expanded=False):
    st.markdown(result.report)
st.download_button("⬇️ 下载报告（.md）", data=result.report,
                   file_name=f"{theme_id}_{as_of}.md", mime="text/markdown")

# 6) 历史回测
st.subheader("⑥ 历史回测")
st.caption("用已训练规律（或默认动量）在历史上逐期回放，统计超额 / IR / 胜率 / 回撤。"
           "⚠️ 若规律在同段历史训练，则为样本内、偏乐观。")
if st.button("▶️ 运行回测"):
    from pathlib import Path as _Path
    import pandas as _pd

    from alpharadar.pipeline import build_panel_from_store
    from alpharadar.backtest.engine import BacktestEngine
    from alpharadar.mining.pattern_miner import PatternLibrary

    res, lib = None, None
    with st.spinner("回放历史中…"):
        built = build_panel_from_store(settings_for_run, store)
        if built is None or built[0].empty:
            st.warning("历史不足以回测（需更长/更多的行情，或先加载演示数据）。")
        else:
            panel, regimes, fwd = built
            lib_path = _Path(store.root) / "patterns.json"
            lib = PatternLibrary.load(lib_path) if lib_path.exists() else None
            res = BacktestEngine(
                top_k=5,
                forward_days=settings.get("horizon", "forward_days", default=63),
            ).run(panel, regimes, fwd, pattern_lib=lib)

    if res is not None and res.n_periods > 0:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("年化超额", f"{(res.annual_excess_return or 0) * 100:.1f}%")
        m2.metric("信息比率 IR", f"{res.information_ratio:.2f}")
        m3.metric("胜率", f"{(res.win_rate or 0) * 100:.0f}%")
        m4.metric("最大回撤", f"{(res.max_drawdown or 0) * 100:.1f}%")
        st.caption(f"规律来源：{'已训练规律库' if lib else '默认动量基线'}　|　{res.n_periods} 期")
        st.line_chart(_pd.DataFrame({"策略": res.equity_curve, "基准": res.benchmark_curve}))
    elif res is not None:
        st.info("数据期数不足，无法生成回测曲线。")

st.divider()
st.caption("⚠️ 本工具仅供研究与教育，所有输出为基于数据的统计分析，"
           "不构成任何投资建议。股市有风险，决策与盈亏自负。")
