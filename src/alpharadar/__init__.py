"""主线雷达 · Mainline Alpha Radar

自上而下、市场状态感知的 A 股主题投资研究系统。

八层架构（自下而上）：
    1. data         数据层      —— 行情/财务/宏观/行业（关联数据）
    2. regime       市场状态     —— 牛熊/风格/风险偏好/流动性
    3. mining       规律挖掘     —— 不同状态下「会涨」的因子共性
    4. theme        主线映射     —— 产业链：主题→瓶颈环节→候选股
    5. fundamental  公司基本面   —— 各季度财务指标打分
    6. selection    选股        —— 综合打分 → Top 1~2
    7. backtest     回测        —— 15 年历史验证规律
    8. report       报告        —— 可解释、可追溯的研究报告

详见 docs/architecture.md。
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
