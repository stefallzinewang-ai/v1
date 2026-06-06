"""第 8 层 · 报告

把整条逻辑链（宏观→行业→主线→公司→候选）渲染成可读、可追溯的研究报告。
每个结论标注数据出处与分项得分。详见 docs/architecture.md 第 8 层。
"""
from .builder import ReportBuilder

__all__ = ["ReportBuilder"]
