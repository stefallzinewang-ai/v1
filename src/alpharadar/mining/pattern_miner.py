"""规律挖掘：从历史中学出「不同市场状态下，会涨的股票」的因子权重。

方法：**按市场状态分组的 IC 加权**（可解释，非黑箱）。
对每个市场状态，统计各因子与前瞻收益的横截面 IC（信息系数），以 IC 为权重，
再用 **walk-forward 样本外验证** 评估稳健性（只用过去训练、未来验证）。
详见 docs/methodology.md §3。

防过拟合是头号纪律：本框架强制样本外评估，且优先 IC 这种有经济含义的弱信号，
权重数量克制，避免曲线拟合。
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


# ══════════════════════════════════════════════════════════════
# 纯统计工具（可离线单测）
# ══════════════════════════════════════════════════════════════
def cross_sectional_ic(df: "pd.DataFrame", factor: str, ret_col: str,
                       min_names: int = 5) -> "pd.Series":
    """逐日横截面 rank-IC（因子值与前瞻收益的斯皮尔曼相关），返回按日期的 IC 序列。"""
    import pandas as pd

    ics = {}
    for date, g in df.groupby("date"):
        sub = g[[factor, ret_col]].dropna()
        if len(sub) < min_names:
            continue
        ic = sub[factor].rank().corr(sub[ret_col].rank())
        if pd.notna(ic):
            ics[date] = ic
    return pd.Series(ics, dtype=float).sort_index()


def ic_summary(ic_series: "pd.Series") -> tuple[float, float]:
    """返回 (IC 均值, IC_IR=均值/标准差)。样本不足时返回 (0,0)。"""
    import pandas as pd

    if ic_series is None or len(ic_series) == 0:
        return 0.0, 0.0
    mean = float(ic_series.mean())
    sd = float(ic_series.std(ddof=0))
    ir = 0.0 if sd == 0 or pd.isna(sd) else mean / sd
    return (0.0 if pd.isna(mean) else mean), ir


def _score_ic(df: "pd.DataFrame", weights: dict[str, float], ret_col: str) -> "pd.Series":
    """用给定权重把因子合成横截面分，再逐日算分数与收益的 rank-IC。"""
    import pandas as pd

    from ..factors.library import standardize

    ics = {}
    for date, g in df.groupby("date"):
        score = None
        for f, w in weights.items():
            if f not in g:
                continue
            s = standardize(g.set_index("symbol")[f]) * w
            score = s if score is None else score.add(s, fill_value=0.0)
        if score is None:
            continue
        ret = g.set_index("symbol")[ret_col]
        sub = pd.concat([score.rename("s"), ret.rename("r")], axis=1).dropna()
        if len(sub) < 5:
            continue
        ic = sub["s"].rank().corr(sub["r"].rank())
        if pd.notna(ic):
            ics[date] = ic
    return pd.Series(ics, dtype=float)


def _train_weights(df: "pd.DataFrame", factor_cols: list[str],
                   ret_col: str) -> dict[str, float]:
    """以各因子 IC 均值为权重（带符号；按绝对值之和归一化，保持尺度稳定）。"""
    raw = {}
    for f in factor_cols:
        mean, _ = ic_summary(cross_sectional_ic(df, f, ret_col))
        raw[f] = mean
    denom = sum(abs(v) for v in raw.values()) or 1.0
    return {f: v / denom for f, v in raw.items()}


# ══════════════════════════════════════════════════════════════
# Pattern & 训练器
# ══════════════════════════════════════════════════════════════
@dataclass
class Pattern:
    """一种市场状态下学到的「上涨共性」——因子到权重的映射 + 表现记录。"""

    regime_key: str
    weights: dict[str, float] = field(default_factory=dict)
    in_sample_ic: float | None = None
    out_sample_ic: float | None = None
    n_obs: int = 0
    notes: str = ""

    def score(self, factor_values: "pd.DataFrame") -> "pd.Series":
        """用学到的权重对横截面因子加权打分（因子先标准化，权重含符号）。

        factor_values：index=symbol，列含 weights 中的因子名。
        """
        import pandas as pd

        from ..factors.library import standardize

        total = None
        for f, w in self.weights.items():
            if f not in factor_values:
                continue
            s = standardize(factor_values[f]) * w
            total = s if total is None else total.add(s, fill_value=0.0)
        return total if total is not None else pd.Series(dtype=float)

    def to_dict(self) -> dict:
        return {
            "regime_key": self.regime_key, "weights": self.weights,
            "in_sample_ic": self.in_sample_ic, "out_sample_ic": self.out_sample_ic,
            "n_obs": self.n_obs, "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Pattern":
        return cls(**d)


class PatternLibrary:
    """{regime_key: Pattern} 的容器，支持 JSON 存取。"""

    def __init__(self, patterns: dict[str, Pattern] | None = None) -> None:
        self.patterns = patterns or {}

    def get(self, regime_key: str) -> Pattern | None:
        return self.patterns.get(regime_key)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: p.to_dict() for k, p in self.patterns.items()}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "PatternLibrary":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls({k: Pattern.from_dict(v) for k, v in data.items()})


class PatternMiner:
    """Walk-forward 训练框架：分市场状态学习因子权重并评估样本外表现。"""

    def __init__(self, forward_days: int = 63, n_splits: int = 4,
                 min_obs: int = 20) -> None:
        self.forward_days = forward_days  # 前瞻收益窗口（约一季度）
        self.n_splits = n_splits          # walk-forward 折数
        self.min_obs = min_obs            # 每个状态最少观测数

    def fit(self, factor_panel: "pd.DataFrame", regime_series: "pd.DataFrame",
            forward_returns: "pd.DataFrame", factor_cols: list[str] | None = None
            ) -> PatternLibrary:
        """按市场状态训练因子权重，返回 PatternLibrary。

        入参（均为 point-in-time，调用方负责保证无未来函数）：
            factor_panel    : 长表 [date, symbol, <factor1>, <factor2>, ...]
            regime_series   : [date, regime_key]
            forward_returns : [date, symbol, fwd_ret]（date→date+H 的前瞻收益）

        要点（防过拟合，决定系统成败）：
            - 滚动样本外：只用过去训练、未来验证；
            - 因子权重 = 状态内各因子 IC（有经济含义的弱信号），数量克制；
            - 同时报告样本内/外 IC，以样本外为准。
        """
        import numpy as np
        import pandas as pd

        if factor_cols is None:
            factor_cols = [c for c in factor_panel.columns if c not in ("date", "symbol")]

        merged = (factor_panel
                  .merge(forward_returns, on=["date", "symbol"], how="inner")
                  .merge(regime_series, on="date", how="inner"))
        merged["date"] = pd.to_datetime(merged["date"])
        if merged.empty:
            return PatternLibrary({})

        # ── walk-forward 收集各状态样本外 IC ──────────────────
        dates = np.array(sorted(merged["date"].unique()))
        oos_ic: dict[str, list[float]] = defaultdict(list)
        if len(dates) >= self.n_splits + 1:
            folds = np.array_split(dates, self.n_splits + 1)
            for i in range(1, len(folds)):
                train_dates = np.concatenate(folds[:i])
                test_dates = folds[i]
                train = merged[merged["date"].isin(train_dates)]
                test = merged[merged["date"].isin(test_dates)]
                for rk, g_tr in train.groupby("regime_key"):
                    if len(g_tr) < self.min_obs:
                        continue
                    w = _train_weights(g_tr, factor_cols, "fwd_ret")
                    g_te = test[test["regime_key"] == rk]
                    if g_te.empty:
                        continue
                    mean_ic, _ = ic_summary(_score_ic(g_te, w, "fwd_ret"))
                    if mean_ic != 0.0:
                        oos_ic[rk].append(mean_ic)

        # ── 用全样本按状态训练最终权重 ───────────────────────
        patterns: dict[str, Pattern] = {}
        for rk, g in merged.groupby("regime_key"):
            if len(g) < self.min_obs:
                continue
            weights = _train_weights(g, factor_cols, "fwd_ret")
            in_ic, _ = ic_summary(_score_ic(g, weights, "fwd_ret"))
            oos = oos_ic.get(rk, [])
            out_ic = float(np.mean(oos)) if oos else None
            patterns[rk] = Pattern(
                regime_key=rk, weights=weights,
                in_sample_ic=round(in_ic, 4),
                out_sample_ic=None if out_ic is None else round(out_ic, 4),
                n_obs=int(len(g)),
                notes=f"IC 加权；walk-forward {len(oos)} 折样本外",
            )
        return PatternLibrary(patterns)
