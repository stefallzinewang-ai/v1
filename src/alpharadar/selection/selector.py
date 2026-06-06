"""综合选股器：加权融合各维度得分，输出可解释的候选清单。

把基本面（成长/质量）、价格类（动量）、主线契合等维度按权重融合成总分，
取 Top N，并保留每只股票的得分明细与人类可读理由，供报告层解释。
权重理想上来自阶段 5 的 Pattern（随市场状态变化）；阶段 5 就绪前用主线
emphasis 作为权重。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping

from ..factors.library import cross_section_score

if TYPE_CHECKING:
    import pandas as pd

# 维度中文标签（报告/理由用）
_DIM_LABELS = {
    "growth": "成长", "quality": "质量", "momentum": "动量",
    "valuation": "估值", "prosperity": "景气", "theme_fit": "主线契合",
    "alpha": "规律信号",
}


@dataclass
class Candidate:
    """一个候选公司及其可解释的得分明细。"""

    symbol: str
    name: str
    total_score: float
    breakdown: dict[str, float] = field(default_factory=dict)  # 维度 → 标准化分数
    reasons: list[str] = field(default_factory=list)           # 人类可读理由
    report_period: str | None = None

    def explain(self) -> str:
        parts = [f"{_DIM_LABELS.get(k, k)}={v:+.2f}" for k, v in self.breakdown.items()]
        return f"{self.name}({self.symbol}) 总分 {self.total_score:+.2f} | " + ", ".join(parts)


class Selector:
    """汇流层：按维度权重融合得分并取 Top N。"""

    def __init__(self, top_n: int = 2) -> None:
        self.top_n = top_n

    def select(self, dimension_scores: Mapping[str, "pd.Series"],
               weights: Mapping[str, float] | None = None,
               names: Mapping[str, str] | None = None,
               periods: Mapping[str, str] | None = None) -> list[Candidate]:
        """融合打分并返回 Top N 候选。

        dimension_scores：{维度名: 横截面标准化分数 Series（index=symbol）}。
        weights：各维度权重（缺省等权；只对传入维度计权并归一化）。
        names/periods：symbol → 名称 / 报告期，用于展示。
        """
        import pandas as pd

        dims = {k: v for k, v in dimension_scores.items() if v is not None and len(v) > 0}
        if not dims:
            return []
        df = pd.DataFrame(dims).fillna(0.0)
        w = {d: (weights or {}).get(d, 0.0) for d in df.columns}
        if sum(w.values()) == 0:
            w = {d: 1.0 for d in df.columns}
        total = cross_section_score({d: df[d] for d in df.columns}, weights=w)
        df = df.assign(total=total).sort_values("total", ascending=False)

        names, periods = names or {}, periods or {}
        out: list[Candidate] = []
        for sym, row in df.iterrows():
            breakdown = {d: float(row[d]) for d in dims}
            out.append(Candidate(
                symbol=sym, name=names.get(sym, sym),
                total_score=float(row["total"]),
                breakdown=breakdown,
                reasons=self._reasons(breakdown, w),
                report_period=periods.get(sym),
            ))
        return out[: self.top_n]

    @staticmethod
    def _reasons(breakdown: dict[str, float], weights: dict[str, float]) -> list[str]:
        """按「分数 × 权重」的贡献从大到小列出理由。"""
        ranked = sorted(breakdown.items(),
                        key=lambda kv: kv[1] * weights.get(kv[0], 0.0), reverse=True)
        reasons = []
        for dim, val in ranked:
            tag = "优势" if val > 0 else ("中性" if abs(val) < 1e-6 else "拖累")
            reasons.append(f"{_DIM_LABELS.get(dim, dim)} {val:+.2f}（{tag}）")
        return reasons
