"""规律挖掘：从历史中学出「不同市场状态下，会涨的股票」的因子权重。

把选股建模成「横截面排序/分类」问题，按市场状态分组训练，
严守无未来函数与样本外纪律。详见 docs/methodology.md §3。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class Pattern:
    """一种市场状态下学到的「上涨共性」——因子到权重的映射 + 表现记录。"""

    regime_key: str                       # 适用的市场状态（如 "bull|growth|high"）
    weights: dict[str, float] = field(default_factory=dict)  # 因子名 → 权重
    in_sample_ic: float | None = None     # 样本内 IC
    out_sample_ic: float | None = None    # 样本外 IC（更重要）
    notes: str = ""

    def score(self, factor_values: "pd.DataFrame") -> "pd.Series":
        """用学到的权重对横截面因子加权打分。待阶段 5 实现。"""
        # TODO(阶段5): 加权求和（因子已标准化），返回每只股票的综合分。
        raise NotImplementedError("Pattern.score 待阶段 5 实现")


class PatternMiner:
    """Walk-forward 训练框架：分市场状态学习因子权重。"""

    def __init__(self, forward_days: int = 63) -> None:
        self.forward_days = forward_days  # 前瞻收益窗口（约一季度）

    def fit(
        self,
        factor_panel: "pd.DataFrame",   # 历史因子（多时点 × 多股票）
        regime_series: "pd.DataFrame",  # 各时点市场状态
        forward_returns: "pd.DataFrame",  # 前瞻收益（标签）
    ) -> dict[str, Pattern]:
        """Walk-forward 训练，按状态返回 {regime_key: Pattern}。

        阶段 5 要点（务必遵守，决定系统成败）：
            - 滚动样本外：只用过去训练、未来验证，绝不全样本拟合；
            - point-in-time：因子按公告日，标签为前瞻超额收益；
            - 含退市股、扣交易成本、剔除不可成交；
            - 优先可解释模型（正则逻辑回归 / 单调 GBDT / IC 加权）。
        """
        # TODO(阶段5): 见 docstring。
        raise NotImplementedError("PatternMiner.fit 待阶段 5 实现，见 roadmap 阶段 5")
