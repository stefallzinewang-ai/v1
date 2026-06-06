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


def standardize(values: "pd.Series", method: str = "zscore") -> "pd.Series":
    """横截面标准化（去极值 + zscore/分位）。待阶段 3 实现。"""
    # TODO(阶段3): winsorize → zscore 或 rank-pct；处理缺失。
    raise NotImplementedError("standardize 待阶段 3 实现")


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
