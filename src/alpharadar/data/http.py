"""轻量 HTTP 客户端：限速 + 指数退避重试 + 浏览器 UA。

数据源（如东方财富）会限速/反爬，统一在这里处理，业务代码只管解析。
"""
from __future__ import annotations

import time
from typing import Any

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


class HttpClient:
    """对 requests 的薄封装，内置限速与重试。"""

    def __init__(
        self,
        rate_limit_per_min: int = 60,
        max_retries: int = 4,
        timeout: float = 10.0,
    ) -> None:
        self.min_interval = 60.0 / max(rate_limit_per_min, 1)
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_call = 0.0
        self._session = None

    def _get_session(self):
        if self._session is None:
            import requests  # 延迟导入，骨架在未装 requests 时也能 import

            self._session = requests.Session()
            self._session.headers.update(DEFAULT_HEADERS)
        return self._session

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict:
        """GET 并解析 JSON，失败时指数退避重试（2s,4s,8s,16s）。

        仅对网络错误、超时、429、5xx 重试；其余 4xx（如 403/404）是客户端/权限
        问题，重试无意义，直接抛出。
        """
        import requests

        session = self._get_session()
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                resp = session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                # 不可重试的客户端错误：直接抛出，不浪费退避时间
                if status is not None and 400 <= status < 500 and status != 429:
                    raise RuntimeError(f"请求被拒绝（HTTP {status}）：{url}") from exc
                last_exc = exc
            except Exception as exc:  # 连接错误/超时/JSON 解析错误 → 可重试
                last_exc = exc
            if attempt < self.max_retries:
                time.sleep(2 ** (attempt + 1))
        raise RuntimeError(f"请求失败（已重试 {self.max_retries} 次）：{url}") from last_exc
