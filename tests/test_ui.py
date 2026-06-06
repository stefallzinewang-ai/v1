"""界面相关测试：演示数据灌入 + Streamlit 应用端到端渲染（不触网）。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

pytest.importorskip("pandas")
pytest.importorskip("pyarrow")


# ── 演示数据 ──────────────────────────────────────────────────
def test_seed_demo_store(tmp_path):
    from alpharadar.data.store import DataStore
    from alpharadar.demo import seed_demo_store

    store = DataStore(root=tmp_path)
    info = seed_demo_store(store, periods=300, universe_size=10)
    assert info["rows"] > 0 and info["financial_rows"] == 6

    bars = store.read_bars()
    assert not bars.empty
    # 指数与候选股都在
    syms = set(bars["symbol"])
    assert "000300.SH" in syms and "300308.SZ" in syms
    assert not store.read_table("financials").empty


def test_demo_data_drives_pipeline(tmp_path):
    from alpharadar.config import Settings
    from alpharadar.data.store import DataStore
    from alpharadar.demo import seed_demo_store
    from alpharadar.pipeline import run_pipeline

    store = DataStore(root=tmp_path)
    seed_demo_store(store)
    settings = Settings(raw={"storage": {"root": str(tmp_path)}, "selection": {"top_n": 2}})
    result = run_pipeline("ai_optical_module", as_of="2021-12-31", settings=settings)
    assert result.regime.key() == "bull|growth|high"
    assert result.activation.active is True
    assert result.candidates and result.candidates[0].symbol == "300308.SZ"


# ── Streamlit 应用 ────────────────────────────────────────────
def test_streamlit_app_renders(tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    from alpharadar.data.store import DataStore
    from alpharadar.demo import seed_demo_store

    # 应用按 cwd 下的 ./data_store 读数；切到临时目录并灌入演示数据
    monkeypatch.chdir(tmp_path)
    seed_demo_store(DataStore(root="./data_store"))

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert any("趋势" in l for l in labels)        # 市场状态指标已渲染
    subheaders = [s.value for s in at.subheader]
    assert any("候选公司" in s for s in subheaders)  # 候选公司区块已渲染
