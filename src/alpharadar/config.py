"""配置加载：全局设置（settings.yaml）与主线配置（themes/*.yaml）。

配置与代码分离是本系统的核心原则之一——产业链、阈值、权重都走 YAML，
便于快速迭代而无需改动代码。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 项目根目录（src/alpharadar/config.py → 上溯三级）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
THEMES_DIR = CONFIG_DIR / "themes"


def _load_yaml(path: Path) -> dict[str, Any]:
    """读取 YAML 文件为 dict。延迟导入 PyYAML，给出友好报错。"""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - 依赖缺失时的引导
        raise ImportError(
            "需要 PyYAML 来读取配置，请先 `pip install -r requirements.txt`。"
        ) from exc
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在：{path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@dataclass
class Settings:
    """全局设置。字段对应 config/settings.example.yaml 的结构。"""

    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Settings":
        """加载 settings.yaml；若不存在则回退到 settings.example.yaml。"""
        if path is None:
            candidate = CONFIG_DIR / "settings.yaml"
            path = candidate if candidate.exists() else CONFIG_DIR / "settings.example.yaml"
        return cls(raw=_load_yaml(Path(path)))

    def get(self, *keys: str, default: Any = None) -> Any:
        """按路径取值，如 settings.get('storage', 'root')。"""
        node: Any = self.raw
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


@dataclass
class ThemeConfig:
    """一条主线（产业链）的配置，对应 themes/*.yaml。"""

    id: str
    name: str
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, theme_id: str) -> "ThemeConfig":
        data = _load_yaml(THEMES_DIR / f"{theme_id}.yaml")
        return cls(id=data.get("id", theme_id), name=data.get("name", theme_id), raw=data)

    @property
    def bottleneck_stage(self) -> dict[str, Any] | None:
        """返回产业链中标记为瓶颈（bottleneck=True）的环节。"""
        stages = self.raw.get("value_chain", {}).get("stages", [])
        for stage in stages:
            if stage.get("bottleneck"):
                return stage
        return None

    @property
    def seed_symbols(self) -> list[str]:
        """候选股池的种子代码列表。"""
        pool = self.raw.get("candidate_pool", {}).get("seed_symbols", [])
        return [item["symbol"] for item in pool if "symbol" in item]


def list_themes() -> list[str]:
    """列出 config/themes 下所有可用主线 id。"""
    if not THEMES_DIR.exists():
        return []
    return sorted(p.stem for p in THEMES_DIR.glob("*.yaml"))
