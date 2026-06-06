"""因子定义与计算。

每个因子统一做：缺失处理 → 去极值 → 标准化 → 方向对齐（越大越好）。
详见 docs/methodology.md §2。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal

if TYPE_CHECKING:
    import pandas as pd

# 五大类因子（与方法论文档一一对应）
FACTOR_CATEGORIES = ("prosperity", "growth", "quality", "momentum", "valuation")

Category = Literal["prosperity", "growth", "quality", "momentum", "valuation"]


@dataclass
class Factor:
    """一个因子的元数据 + 计算函数。

    compute(panel) 返回横截面因子值（index=symbol, value=因子原始值）。
    方向 direction: "up" 表示越大越好，"down" 表示越小越好（计算后会统一翻转）。
    """

    name: str
    category: Category
    direction: Literal["up", "down"]
    description: str
    compute: Callable[["pd.DataFrame"], "pd.Series"] | None = None


def standardize(values: "pd.Series", method: str = "zscore",
                winsor: float = 0.05, direction: str = "up") -> "pd.Series":
    """横截面标准化：去极值 → zscore/分位 → 方向对齐（结果越大越好）。

    method: 'zscore'（均值0方差1）或 'rank'（0~1 分位，对极端值更稳健）。
    direction='down' 时取负，使「越小越好」的因子（如估值）也变成越大越好。
    缺失值置中性（zscore→0，rank→0.5）。
    """
    import pandas as pd

    s = pd.to_numeric(values, errors="coerce")
    if s.notna().sum() == 0:
        return pd.Series(0.0, index=s.index)
    lo, hi = s.quantile(winsor), s.quantile(1 - winsor)
    s = s.clip(lo, hi)
    if method == "rank":
        out = s.rank(pct=True)
        out = out.fillna(0.5)
    else:
        mu, sd = s.mean(), s.std(ddof=0)
        out = pd.Series(0.0, index=s.index) if (sd == 0 or pd.isna(sd)) else (s - mu) / sd
        out = out.fillna(0.0)
    return -out if direction == "down" else out


def cross_section_score(factors: dict[str, "pd.Series"],
                        weights: dict[str, float] | None = None) -> "pd.Series":
    """把多个（已标准化的）因子按权重线性合成横截面综合分。

    weights 缺省等权；只对传入的因子计权并归一化。
    """
    import pandas as pd

    if not factors:
        return pd.Series(dtype=float)
    df = pd.DataFrame(factors)
    w = {k: (weights or {}).get(k, 1.0) for k in df.columns}
    total_w = sum(w.values()) or 1.0
    return sum(df[k] * (w[k] / total_w) for k in df.columns)


def compute_momentum(bars: "pd.DataFrame", as_of, lookback: int = 63) -> "pd.Series":
    """动量因子：各股票截至 as_of 的近 lookback 个交易日收益（横截面，index=symbol）。"""
    import pandas as pd

    as_of_ts = pd.to_datetime(as_of) if as_of is not None else None
    out: dict[str, float] = {}
    for sym, g in bars.groupby("symbol"):
        g = g.sort_values("date")
        if as_of_ts is not None:
            g = g[pd.to_datetime(g["date"]) <= as_of_ts]
        if len(g) > lookback:
            out[sym] = float(g["close"].iloc[-1] / g["close"].iloc[-1 - lookback] - 1.0)
    return pd.Series(out, dtype=float)


# 因子注册表骨架——阶段 3 在此登记具体因子及其 compute 实现。
REGISTRY: dict[str, Factor] = {
    "revenue_yoy": Factor(
        name="revenue_yoy", category="growth", direction="up",
        description="营业收入同比增速",
    ),
    "net_profit_accel": Factor(
        name="net_profit_accel", category="growth", direction="up",
        description="净利增速的边际变化（二阶），衡量加速度",
    ),
    "roe": Factor(
        name="roe", category="quality", direction="up", description="净资产收益率",
    ),
    "gross_margin_trend": Factor(
        name="gross_margin_trend", category="quality", direction="up",
        description="毛利率趋势（良率/成本改善）",
    ),
    "mom_3m": Factor(
        name="mom_3m", category="momentum", direction="up", description="近 3 月相对行业收益",
    ),
    "pe_percentile": Factor(
        name="pe_percentile", category="valuation", direction="down",
        description="PE 历史分位（越低越好，防追高）",
    ),
    "industry_prosperity": Factor(
        name="industry_prosperity", category="prosperity", direction="up",
        description="行业景气度（出货/订单/量价合成）",
    ),
}
