"""Shared HTTP helpers for hardening gates."""

from __future__ import annotations

from fastapi import HTTPException, Request


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def reject(code: str, message: str, status: int = 403) -> None:
    raise HTTPException(status_code=status, detail={"error": {"code": code, "message": message}})


def enforce_live_api_rate(request: Request) -> None:
    """Per-IP rate limit for chat / claim prepare / cancel start."""
    settings = request.app.state.settings
    limiter = request.app.state.rate_limiter
    ip = client_ip(request)
    ok = limiter.allow(
        f"live:{ip}",
        limit=settings.live_api_rate_limit,
        window_s=settings.live_api_rate_window_s,
    )
    if not ok:
        reject(
            "rate_limited",
            "Too many requests from this address. Try again shortly.",
            status=429,
        )
