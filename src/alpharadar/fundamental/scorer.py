"""公司基本面打分器。

侧重成长加速度、产能扩张（capex）、估值分位。详见 docs/methodology.md §5。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


class FundamentalScorer:
    """对一组公司按季度财务打分，输出分项 + 总分。"""

    def score(self, financials: "pd.DataFrame", as_of: str) -> "pd.DataFrame":
        """返回 index=symbol、含各分项得分与 total 的 DataFrame。

        阶段 3 要点：
            - 用 ann_date <= as_of 的最新一期，防未来函数；
            - 成长看增速及其加速度；产能看 capex/在建工程；
            - 质量看毛利率/ROE/现金流；估值看历史分位（越低越好）。
        """
        # TODO(阶段3): 见 docstring。
        raise NotImplementedError("FundamentalScorer.score 待阶段 3 实现")
