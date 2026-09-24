"""Service configuration, read from environment variables (docs/03-link-service.md §3.1)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

AUTH_SCHEMES = ("bearer", "mcc")


@dataclass(frozen=True)
class Settings:
    cds_base_url: str
    apds_base_url: str
    cds_token: str | None = None
    apds_token: str | None = None
    apds_auth_scheme: str = "bearer"
    webhook_token: str | None = None
    default_radius_m: int = 400
    http_timeout_ms: int = 10_000
    host: str = "0.0.0.0"
    port: int = 8080

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Settings:
        return cls(
            cds_base_url=_base_url(env, "CDS_BASE_URL"),
            apds_base_url=_base_url(env, "APDS_BASE_URL"),
            cds_token=env.get("CDS_TOKEN") or None,
            apds_token=env.get("APDS_TOKEN") or None,
            apds_auth_scheme=_choice(env, "APDS_AUTH_SCHEME", AUTH_SCHEMES, "bearer"),
            webhook_token=env.get("LINK_WEBHOOK_TOKEN") or None,
            default_radius_m=_int(env, "DEFAULT_RADIUS_M", 400, 1, 5000),
            http_timeout_ms=_int(env, "HTTP_TIMEOUT_MS", 10_000, 100, 120_000),
            host=env.get("HOST") or "0.0.0.0",
            port=_int(env, "PORT", 8080, 1, 65_535),
        )


def _base_url(env: Mapping[str, str], name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute http(s) URL")
    return value.rstrip("/")


def _int(env: Mapping[str, str], name: str, default: int, lo: int, hi: int) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    if not raw.strip().isdigit():
        raise ValueError(f"{name} must be an integer")
    value = int(raw)
    if not lo <= value <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return value


def _choice(env: Mapping[str, str], name: str, allowed: tuple[str, ...], default: str) -> str:
    value = (env.get(name) or default).strip().lower()
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    return value
