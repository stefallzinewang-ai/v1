"""公司基本面打分器。

对候选池里的公司按各季度财务指标打分，强调边际变化与兑现度：
    成长 growth   ← 营收同比、净利同比、净利增速的加速度（边际变化）
    质量 quality  ← 销售毛利率、ROE
所有指标做横截面标准化后合成。估值/动量等价格类因子在 factors 层，
由选股层（阶段 6）再融合。详见 docs/methodology.md §5。

point-in-time：只用 ann_date（公告日）<= as_of 的最新一期，杜绝未来函数。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from ..factors.library import standardize, cross_section_score

if TYPE_CHECKING:
    pass

# 本层涉及的维度（价格类的 momentum/valuation 不在此）
_DIMENSIONS = ("growth", "quality")


class FundamentalScorer:
    """对一组公司按季度财务打分，输出分项 + 总分。"""

    def __init__(self, emphasis: dict[str, float] | None = None,
                 method: str = "zscore") -> None:
        # emphasis 来自主线配置 fundamental_emphasis；此处只取 growth/quality 两项
        self.emphasis = emphasis or {}
        self.method = method

    def latest_pit(self, financials: pd.DataFrame, as_of) -> pd.DataFrame:
        """每只股票取 ann_date<=as_of 的最新一期，并附上一期净利增速（算加速度）。"""
        if financials.empty:
            return financials
        df = financials.copy()
        df["ann_date"] = pd.to_datetime(df["ann_date"])
        df["report_period"] = pd.to_datetime(df["report_period"])
        as_of_ts = pd.to_datetime(as_of)
        df = df[df["ann_date"] <= as_of_ts].sort_values(["symbol", "report_period"])

        rows = []
        for sym, g in df.groupby("symbol"):
            if g.empty:
                continue
            cur = g.iloc[-1].copy()
            cur["net_profit_yoy_prev"] = g.iloc[-2]["net_profit_yoy"] if len(g) >= 2 else None
            rows.append(cur)
        if not rows:
            return df.iloc[0:0]
        out = pd.DataFrame(rows).set_index("symbol")
        # 净利增速的边际变化（加速度）：当期同比 − 上期同比
        out["net_profit_accel"] = out["net_profit_yoy"] - out["net_profit_yoy_prev"]
        return out

    def score(self, financials: pd.DataFrame, as_of) -> pd.DataFrame:
        """返回 index=symbol，含 growth/quality 分项与 total 的 DataFrame。"""
        pit = self.latest_pit(financials, as_of)
        if pit.empty:
            return pd.DataFrame(columns=["report_period", "ann_date", *_DIMENSIONS, "total"])

        # 成长：营收同比、净利同比、净利增速加速度（等权合成）
        growth = cross_section_score({
            "revenue_yoy": standardize(pit["revenue_yoy"], self.method),
            "net_profit_yoy": standardize(pit["net_profit_yoy"], self.method),
            "net_profit_accel": standardize(pit["net_profit_accel"], self.method),
        })
        # 质量：毛利率、ROE
        quality = cross_section_score({
            "gross_margin": standardize(pit["gross_margin"], self.method),
            "roe": standardize(pit["roe"], self.method),
        })

        result = pd.DataFrame({
            "report_period": pit["report_period"].dt.date,
            "ann_date": pit["ann_date"].dt.date,
            "growth": growth,
            "quality": quality,
        })
        # 总分：按主线 emphasis 在本层维度间加权（缺省等权）
        w = {d: self.emphasis.get(d, 1.0) for d in _DIMENSIONS}
        result["total"] = cross_section_score(
            {d: result[d] for d in _DIMENSIONS}, weights=w)
        return result.sort_values("total", ascending=False)
