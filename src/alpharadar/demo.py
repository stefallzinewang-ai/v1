"""演示数据：在本地存储里灌入一批合成数据，让整套系统/界面在离线环境也能跑通。

⚠️ 这是**人造数据**，仅用于演示界面与流程，不含任何真实市场信息。
真实使用请用 `alpharadar sync` 采集真实行情。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .data.store import DataStore

if TYPE_CHECKING:
    import pandas as pd

# 演示用：构造成 bull|growth|high 状态的指数
_DEMO_INDICES = {
    "000300.SH": (100, 180),   # 宽基上行
    "399006.SZ": (100, 160),   # 成长跑赢
    "000016.SH": (100, 108),   # 价值/大盘
    "000852.SH": (100, 150),   # 小盘跑赢
}

# 演示候选股（光模块主线）——差异化趋势，使排序有区分度
_DEMO_CANDIDATES = {
    "300308.SZ": (100, 200),
    "300502.SZ": (100, 135),
    "300394.SZ": (100, 112),
}


def _bars(sym: str, start_val: float, end_val: float, dates) -> "pd.DataFrame":
    import numpy as np
    import pandas as pd

    vals = np.linspace(start_val, end_val, len(dates))
    return pd.DataFrame({"symbol": sym, "date": dates, "open": vals, "high": vals,
                         "low": vals, "close": vals, "volume": 1.0, "amount": 1.0,
                         "turnover": 0.1})


def seed_demo_store(store: DataStore, periods: int = 500,
                    universe_size: int = 20, seed: int = 0) -> dict:
    """灌入演示数据：指数 + 候选股 + 一批随机游走股票（供规律挖掘）+ 财务。

    返回写入概况 dict。
    """
    import numpy as np
    import pandas as pd

    store.ensure_dirs()
    dates = pd.bdate_range("2021-01-04", periods=periods)
    rng = np.random.default_rng(seed)

    frames = [_bars(s, a, b, dates) for s, (a, b) in _DEMO_INDICES.items()]
    frames += [_bars(s, a, b, dates) for s, (a, b) in _DEMO_CANDIDATES.items()]

    # 额外的随机游走股票池（带轻微漂移），让规律挖掘有足够横截面
    for i in range(universe_size):
        drift = rng.normal(0, 0.0008)
        steps = rng.normal(drift, 0.02, len(dates))
        prices = 100 * np.exp(np.cumsum(steps))
        df = pd.DataFrame({"symbol": f"{600100 + i}.SH", "date": dates,
                           "open": prices, "high": prices, "low": prices,
                           "close": prices, "volume": 1.0, "amount": 1.0, "turnover": 0.1})
        frames.append(df)

    bars = pd.concat(frames, ignore_index=True)
    store.write_bars(bars)

    # 候选股财务（含公告日）——300308 成长与质量最强
    fin = pd.DataFrame([
        ("300308.SZ", "2021-03-31", "2021-04-25", 50, 80, 9, 250, 33.0, 7.0, 0.5),
        ("300308.SZ", "2020-12-31", "2021-04-15", 100, 10, 20, 30, 30.0, 15.0, 1.0),
        ("300502.SZ", "2021-03-31", "2021-04-28", 40, 12, 4, 20, 23.0, 4.0, 0.2),
        ("300502.SZ", "2020-12-31", "2021-04-10", 80, 5, 10, 5, 22.0, 8.0, 0.3),
        ("300394.SZ", "2021-03-31", "2021-04-22", 30, 8, 3, 10, 25.0, 6.0, 0.2),
        ("300394.SZ", "2020-12-31", "2021-04-12", 60, 6, 8, 8, 24.0, 7.0, 0.3),
    ], columns=["symbol", "report_period", "ann_date", "revenue", "revenue_yoy",
                "net_profit", "net_profit_yoy", "gross_margin", "roe", "ocf"])
    store.write_table("financials", fin, subset=["symbol", "report_period"])

    # 行业成分（演示增强）
    members = pd.DataFrame({
        "industry_code": ["BK0457", "BK0457"],
        "symbol": ["301205", "300308"],
        "name": ["联特科技", "中际旭创"],
    })
    store.write_table("industry", members, subset=["industry_code", "symbol"])

    return {
        "indices": len(_DEMO_INDICES),
        "candidates": len(_DEMO_CANDIDATES),
        "universe": universe_size,
        "rows": int(len(bars)),
        "financial_rows": int(len(fin)),
    }
