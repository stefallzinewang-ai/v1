"""综合选股器：加权融合各维度得分，输出可解释的候选清单。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from ..mining.pattern_miner import Pattern


@dataclass
class Candidate:
    """一个候选公司及其可解释的得分明细。"""

    symbol: str
    name: str
    total_score: float
    breakdown: dict[str, float] = field(default_factory=dict)  # 维度 → 分数
    reasons: list[str] = field(default_factory=list)           # 人类可读理由

    def explain(self) -> str:
        parts = [f"{k}={v:+.2f}" for k, v in self.breakdown.items()]
        return f"{self.name}({self.symbol}) 总分 {self.total_score:+.2f} | " + ", ".join(parts)


class Selector:
    """汇流层：把各层分数按市场状态权重融合，取 Top N。"""

    def __init__(self, top_n: int = 2) -> None:
        self.top_n = top_n

    def select(
        self,
        pattern: "Pattern",
        factor_scores: "pd.DataFrame",
        fundamental_scores: "pd.DataFrame",
        theme_fit: "pd.Series",
    ) -> list[Candidate]:
        """融合打分并返回 Top N 候选。

        阶段 6 要点：
            - 权重来自 Pattern（按当前市场状态），而非拍脑袋；
            - 总分 = Σ w_i · 维度_i（含主线契合度 theme_fit）；
            - 保留 breakdown 与 reasons，供报告层解释；
            - 应用 settings 的市值/流动性过滤后再取 Top N。
        """
        # TODO(阶段6): 见 docstring。
        raise NotImplementedError("Selector.select 待阶段 6 实现")
