"""训练面板构建：从已采集的行情/指数，组装规律挖掘所需的三张表。

输出（喂给 PatternMiner.fit）：
    factor_panel    [date, symbol, <价格类因子...>]
    regime_series   [date, regime_key]
    forward_returns [date, symbol, fwd_ret]

价格类因子从行情矩阵向量化计算；前瞻收益按交易日偏移（point-in-time，
date 当天的因子对应 date→date+H 的未来收益，训练时不会用到未来信息）。
财务类因子（成长/质量）可后续按 ann_date 对齐加入。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from ..regime.detector import RegimeDetector


def price_factors(close_wide: "pd.DataFrame") -> dict[str, "pd.DataFrame"]:
    """从宽表收盘价（index=date, columns=symbol）算价格类因子宽表。"""
    ret1 = close_wide.pct_change()
    return {
        "mom_63": close_wide.pct_change(63),    # 中期动量（约一季度）
        "mom_252": close_wide.pct_change(252),  # 长期动量（约一年）
        "reversal_5": -close_wide.pct_change(5),  # 短期反转
        "vol_21": ret1.rolling(21).std(),         # 波动率（符号由 IC 学习）
    }


_FIN_FACTORS = ["revenue_yoy", "net_profit_yoy", "gross_margin", "roe"]


def _attach_financials(factor_panel: "pd.DataFrame", financials: "pd.DataFrame") -> "pd.DataFrame":
    """把财务因子按 point-in-time（ann_date<=调仓日的最新一期）并入因子面板。"""
    import pandas as pd

    fin = financials.copy()
    fin["ann_date"] = pd.to_datetime(fin["ann_date"])
    keep = ["ann_date", "symbol"] + [c for c in _FIN_FACTORS if c in fin.columns]
    fin = fin[keep].dropna(subset=["ann_date"]).sort_values("ann_date")
    left = factor_panel.sort_values("date")
    merged = pd.merge_asof(left, fin, left_on="date", right_on="ann_date",
                           by="symbol", direction="backward")
    return merged.drop(columns=["ann_date"], errors="ignore")


def build_training_panel(bars: "pd.DataFrame", index_bars: "pd.DataFrame",
                         detector: "RegimeDetector", forward_days: int = 63,
                         rebalance_freq: str = "ME", min_history: int = 252,
                         financials: "pd.DataFrame | None" = None):
    """组装训练三表。

    bars/index_bars：长表（列同 bars schema，至少含 symbol,date,close）。
    financials：可选，含财务因子，按 ann_date 做 point-in-time 对齐并入。
    rebalance_freq：调仓频率（pandas 频率别名，'ME'=月末）。
    """
    import pandas as pd

    bars = bars.copy()
    bars["date"] = pd.to_datetime(bars["date"])
    close = bars.pivot_table(index="date", columns="symbol", values="close").sort_index()

    # 前瞻收益（按交易日偏移）：每个 symbol 列 shift(-H)
    fwd = close.shift(-forward_days) / close - 1.0

    factors = price_factors(close)

    # 调仓日：在数据范围内、且已有足够历史
    all_dates = close.index
    if len(all_dates) <= min_history:
        rebal_dates = all_dates[min_history:]
    else:
        marks = pd.Series(1, index=all_dates).resample(rebalance_freq).last().dropna().index
        rebal_dates = [d for d in all_dates if d in set(marks) and d >= all_dates[min_history]]

    # factor_panel
    panel_rows = []
    for name, mat in factors.items():
        sub = mat.loc[mat.index.isin(rebal_dates)]
        melted = sub.reset_index().melt(id_vars="date", var_name="symbol", value_name=name)
        panel_rows.append(melted)
    if not panel_rows:
        empty = pd.DataFrame()
        return empty, empty, empty
    factor_panel = panel_rows[0]
    for extra in panel_rows[1:]:
        factor_panel = factor_panel.merge(extra, on=["date", "symbol"], how="outer")

    # 可选：并入 point-in-time 财务因子（成长/质量）
    if financials is not None and len(financials) > 0:
        factor_panel = _attach_financials(factor_panel, financials)

    # forward_returns
    fsub = fwd.loc[fwd.index.isin(rebal_dates)]
    forward_returns = (fsub.reset_index().melt(id_vars="date", var_name="symbol",
                                               value_name="fwd_ret").dropna(subset=["fwd_ret"]))

    # regime_series（每个调仓日判一次状态）
    regimes = []
    for d in rebal_dates:
        try:
            rk = detector.detect(index_bars, as_of=d.strftime("%Y-%m-%d")).key()
        except Exception:
            rk = "unknown"
        regimes.append({"date": d, "regime_key": rk})
    regime_series = pd.DataFrame(regimes)

    return factor_panel, regime_series, forward_returns
