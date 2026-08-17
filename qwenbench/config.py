from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_HTTP_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_REALTIME_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
DEFAULT_FLASH_MODEL = "qwen3-asr-flash-2026-02-10"
DEFAULT_REALTIME_MODEL = "qwen3-asr-flash-realtime-2026-02-10"


class MissingCredentials(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    api_key: str
    http_base: str
    realtime_url: str
    proxy: str | None
    flash_model: str
    realtime_model: str

    @classmethod
    def env_proxy(cls) -> str | None:
        load_dotenv()
        return os.environ.get("DASHSCOPE_PROXY") or None

    @classmethod
    def from_env(cls, proxy: str | None = None) -> "Settings":
        """Read settings, connecting directly unless a proxy is passed in.

        `DASHSCOPE_PROXY` is deliberately not applied on its own. A proxy adds
        an unpredictable hop to every timing, and a benchmark that silently
        inherited one from the environment would publish numbers that nobody
        else could reproduce or interpret.
        """
        load_dotenv()
        key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not key:
            raise MissingCredentials(
                "DASHSCOPE_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        return cls(
            api_key=key,
            http_base=os.environ.get("DASHSCOPE_HTTP_BASE", DEFAULT_HTTP_BASE),
            realtime_url=os.environ.get("DASHSCOPE_REALTIME_URL", DEFAULT_REALTIME_URL),
            proxy=proxy,
            flash_model=os.environ.get("QWEN_FLASH_MODEL", DEFAULT_FLASH_MODEL),
            realtime_model=os.environ.get("QWEN_REALTIME_MODEL", DEFAULT_REALTIME_MODEL),
        )

    @property
    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def describe(self) -> str:
        route = self.proxy or "direct"
        return (
            f"flash={self.flash_model} realtime={self.realtime_model} route={route}"
        )
