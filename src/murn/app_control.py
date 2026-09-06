from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from murn.config import settings


async def _launch(path: Path, *args: str) -> dict[str, Any]:
    executable = path.expanduser().resolve()
    if not executable.is_file():
        return {
            "ok": False,
            "error": f"launcher not found: {executable}",
        }

    try:
        process = await asyncio.create_subprocess_exec(
            str(executable),
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "pid": process.pid, "launcher": str(executable)}


async def open_orbital() -> dict[str, Any]:
    return await _launch(settings.orbital_launcher)


async def open_murn_desktop() -> dict[str, Any]:
    return await _launch(settings.desktop_launcher)
