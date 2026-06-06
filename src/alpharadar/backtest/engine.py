"""回测引擎：严格无未来函数的事件回放。

在每个调仓点，用「当时可得」的因子给股票池打分，取 Top K 等权持有一个前瞻期，
把各期收益链成净值曲线，对比基准（股票池等权），统计年化超额/IR/胜率/回撤。

打分可由已训练的规律库（PatternLibrary，按当期市场状态取权重）驱动，
也可退化为单因子基线（默认中期动量）。

⚠️ 若回测用的 Pattern 是在同一段历史上训练的，则为**样本内**评估，会偏乐观；
真正的稳健性以 walk-forward 样本外（见 mining）或滚动重训为准。本引擎支持
传入「按时点滚动训练」的外部打分函数以做样本外回测。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import pandas as pd
    from ..mining.pattern_miner import PatternLibrary


@dataclass
class BacktestResult:
    """回测统计结果。"""

    annual_return: float | None = None          # 策略年化
    annual_benchmark: float | None = None        # 基准年化
    annual_excess_return: float | None = None    # 年化超额
    information_ratio: float | None = None        # 信息比率
    win_rate: float | None = None                 # 跑赢基准的期数占比
    max_drawdown: float | None = None             # 策略最大回撤
    n_periods: int = 0
    by_regime: dict[str, dict] = field(default_factory=dict)
    equity_curve: "pd.Series | None" = None       # 策略净值
    benchmark_curve: "pd.Series | None" = None    # 基准净值
    periods: "pd.DataFrame | None" = None         # 每期明细

    def summary(self) -> str:
        def pct(x):
            return "—" if x is None else f"{x * 100:.1f}%"
        return (f"年化 {pct(self.annual_return)} | 基准 {pct(self.annual_benchmark)} | "
                f"超额 {pct(self.annual_excess_return)} | IR "
                f"{'—' if self.information_ratio is None else f'{self.information_ratio:.2f}'} | "
                f"胜率 {pct(self.win_rate)} | 最大回撤 {pct(self.max_drawdown)} | "
                f"{self.n_periods} 期")


def _max_drawdown(equity: "pd.Series") -> float:
    roll_max = equity.cummax()
    dd = equity / roll_max - 1.0
    return float(dd.min()) if len(dd) else 0.0


class BacktestEngine:
    """事件回放回测器。"""

    def __init__(self, top_k: int = 5, forward_days: int = 63) -> None:
        self.top_k = top_k
        self.forward_days = forward_days

    def run(self, factor_panel: "pd.DataFrame", regime_series: "pd.DataFrame",
            forward_returns: "pd.DataFrame",
            pattern_lib: "PatternLibrary | None" = None,
            factor_cols: list[str] | None = None,
            score_fn: "Callable | None" = None) -> BacktestResult:
        """回放回测。

        三表同 mining 的输入（point-in-time）。打分优先级：
            score_fn(date, regime_key, factors_df) > pattern_lib[regime] > 默认 mom_63。
        """
        import numpy as np
        import pandas as pd

        from ..factors.library import standardize

        if factor_cols is None:
            factor_cols = [c for c in factor_panel.columns if c not in ("date", "symbol")]

        merged = (factor_panel
                  .merge(forward_returns, on=["date", "symbol"], how="inner")
                  .merge(regime_series, on="date", how="inner"))
        merged["date"] = pd.to_datetime(merged["date"])
        if merged.empty:
            return BacktestResult()

        # 非重叠调仓：在月度面板上按前瞻期跨度抽样，避免持有期重叠
        all_dates = np.array(sorted(merged["date"].unique()))
        stride = max(1, round(self.forward_days / 21))
        rebal_dates = list(all_dates[::stride])

        def _score(date, rk, g: "pd.DataFrame") -> "pd.Series":
            fv = g.set_index("symbol")[factor_cols]
            if score_fn is not None:
                return score_fn(date, rk, fv)
            if pattern_lib is not None:
                pat = pattern_lib.get(rk)
                if pat is not None:
                    return pat.score(fv)
            # 默认基线：中期动量
            base = "mom_63" if "mom_63" in factor_cols else factor_cols[0]
            return standardize(fv[base])

        rows = []
        for date in rebal_dates:
            g = merged[merged["date"] == date]
            if g.empty:
                continue
            rk = g["regime_key"].iloc[0]
            scores = _score(date, rk, g).dropna()
            if len(scores) < 2:
                continue
            ret_by_sym = g.set_index("symbol")["fwd_ret"]
            picks = scores.sort_values(ascending=False).head(self.top_k).index
            strat_ret = float(ret_by_sym.reindex(picks).dropna().mean())
            bench_ret = float(ret_by_sym.dropna().mean())
            if np.isnan(strat_ret) or np.isnan(bench_ret):
                continue
            rows.append({"date": date, "regime_key": rk,
                         "strat": strat_ret, "bench": bench_ret,
                         "excess": strat_ret - bench_ret})

        if not rows:
            return BacktestResult()
        periods = pd.DataFrame(rows).set_index("date").sort_index()

        # 净值与指标
        ppy = 252.0 / self.forward_days  # 每年期数
        n = len(periods)
        eq = (1 + periods["strat"]).cumprod()
        bench_eq = (1 + periods["bench"]).cumprod()
        ann = float(eq.iloc[-1] ** (ppy / n) - 1)
        bench_ann = float(bench_eq.iloc[-1] ** (ppy / n) - 1)
        ex = periods["excess"]
        ex_sd = float(ex.std(ddof=0))
        ir = 0.0 if ex_sd == 0 else float(ex.mean() / ex_sd * np.sqrt(ppy))
        by_regime = {
            rk: {"n": int(len(g)), "excess_mean": float(g["excess"].mean())}
            for rk, g in periods.groupby("regime_key")
        }
        return BacktestResult(
            annual_return=round(ann, 4), annual_benchmark=round(bench_ann, 4),
            annual_excess_return=round(ann - bench_ann, 4),
            information_ratio=round(ir, 3),
            win_rate=round(float((ex > 0).mean()), 3),
            max_drawdown=round(_max_drawdown(eq), 4),
            n_periods=n, by_regime=by_regime,
            equity_curve=eq, benchmark_curve=bench_eq, periods=periods,
        )
