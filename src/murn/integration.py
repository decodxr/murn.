from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

from murn.app_control import open_murn_desktop, open_orbital
from murn.providers.orbital import OrbitalProvider


def build_integration_router(browser: OrbitalProvider) -> APIRouter:
    router = APIRouter(prefix="/v1/integration", tags=["integration"])

    @router.get("/status")
    async def integration_status() -> dict[str, Any]:
        browser_status, browser_tabs = await asyncio.gather(
            browser.status(),
            _safe_tabs(browser),
        )
        return {
            "murn": True,
            "orbital": browser_status,
            "tabs": browser_tabs,
        }

    @router.post("/open-orbital")
    async def integration_open_orbital() -> dict[str, Any]:
        status = await browser.status()
        if status.get("connected"):
            return {"ok": True, "already_running": True, **status}
        result = await open_orbital()
        if result.get("ok"):
            # Give Chromium a short head start so the UI can immediately show a
            # useful connected state when the user clicks the button.
            for _ in range(12):
                await asyncio.sleep(0.25)
                if await browser.health():
                    result["connected"] = True
                    break
        return result

    @router.post("/open-murn")
    async def integration_open_murn() -> dict[str, Any]:
        return await open_murn_desktop()

    return router


async def _safe_tabs(browser: OrbitalProvider) -> list[dict[str, Any]]:
    try:
        payload = await browser.tabs()
        return list(payload.get("tabs") or [])
    except Exception:
        return []
