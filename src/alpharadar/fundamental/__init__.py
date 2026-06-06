"""第 5 层 · 公司基本面打分

对主线圈定的股票池逐家按季度财务打分，强调边际变化与兑现度。
详见 docs/methodology.md §5。
"""
from .scorer import FundamentalScorer

__all__ = ["FundamentalScorer"]
