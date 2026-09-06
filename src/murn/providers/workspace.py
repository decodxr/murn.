from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


_SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "dist", "build",
    "out", "target", "__pycache__", ".cache", ".mypy_cache", ".pytest_cache",
}
_SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".7z",
    ".tar", ".gz", ".xz", ".mp3", ".wav", ".mp4", ".mkv", ".bin", ".so",
    ".dll", ".exe", ".onnx", ".safetensors", ".gguf", ".db", ".sqlite",
}


class WorkspaceProvider:
    """Read-only project inspection limited to configured roots."""

    def __init__(self, roots: str | list[str], max_file_chars: int = 40000) -> None:
        if isinstance(roots, str):
            raw = [item.strip() for item in roots.split(";") if item.strip()]
        else:
            raw = list(roots)
        self.roots = [Path(item).expanduser().resolve() for item in raw]
        self.max_file_chars = max(2000, int(max_file_chars))

    @property
    def configured(self) -> bool:
        return any(root.is_dir() for root in self.roots)

    def _allowed(self, path: Path) -> Path:
        resolved = path.expanduser().resolve()
        for root in self.roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise ValueError("Path is outside configured workspace roots.")

    def _resolve(self, path: str | None) -> Path:
        value = str(path or "").strip()
        if not value:
            for root in self.roots:
                if root.exists():
                    return root
            raise ValueError("No workspace root is available.")
        candidate = Path(value).expanduser()
        if candidate.is_absolute():
            return self._allowed(candidate)
        for root in self.roots:
            resolved = (root / candidate).resolve()
            if resolved.exists():
                return self._allowed(resolved)
        if not self.roots:
            raise ValueError("No workspace root is configured.")
        return self._allowed((self.roots[0] / candidate).resolve())

    @staticmethod
    def _git_env() -> dict[str, str]:
        env = os.environ.copy()
        # Keep fixed read-only git inspection from inheriting user-level helpers.
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        env["GIT_OPTIONAL_LOCKS"] = "0"
        return env

    def roots_info(self) -> dict[str, Any]:
        return {
            "roots": [str(root) for root in self.roots if root.exists()],
            "read_only": True,
        }

    def list(self, path: str | None = None, depth: int = 2, limit: int = 220) -> dict[str, Any]:
        base = self._resolve(path)
        if not base.is_dir():
            raise ValueError(f"Not a directory: {base}")
        depth = max(0, min(4, int(depth)))
        limit = max(1, min(600, int(limit)))
        items: list[dict[str, Any]] = []

        def walk(directory: Path, level: int) -> None:
            if len(items) >= limit or level > depth:
                return
            try:
                children = sorted(
                    directory.iterdir(),
                    key=lambda item: (not item.is_dir(), item.name.lower()),
                )
            except OSError:
                return

            for child in children:
                if len(items) >= limit:
                    break
                if child.name in _SKIP_DIRS or child.is_symlink():
                    continue
                try:
                    safe_child = self._allowed(child)
                    is_dir = safe_child.is_dir()
                    is_file = safe_child.is_file()
                    size = safe_child.stat().st_size if is_file else None
                    rel = safe_child.relative_to(base)
                except (OSError, ValueError):
                    continue

                items.append({
                    "path": str(rel),
                    "type": "dir" if is_dir else "file",
                    "size": size,
                })
                if is_dir and level < depth:
                    walk(safe_child, level + 1)

        walk(base, 0)
        return {"base": str(base), "items": items, "truncated": len(items) >= limit}

    def read(self, path: str, start_line: int = 1, end_line: int | None = None) -> dict[str, Any]:
        file_path = self._resolve(path)
        if not file_path.is_file():
            raise ValueError(f"Not a file: {file_path}")
        if file_path.suffix.lower() in _SKIP_SUFFIXES or file_path.stat().st_size > 2_000_000:
            raise ValueError("Refusing to read binary or oversized file.")
        text = file_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start = max(1, int(start_line))
        end = len(lines) if end_line is None else max(start, min(len(lines), int(end_line)))
        selected = lines[start - 1:end]
        content = "\n".join(selected)
        truncated = False
        if len(content) > self.max_file_chars:
            content = content[: self.max_file_chars] + "\n…"
            truncated = True
        return {
            "path": str(file_path),
            "start_line": start,
            "end_line": end,
            "total_lines": len(lines),
            "content": content,
            "truncated": truncated,
        }

    def search(self, query: str, path: str | None = None, limit: int = 40) -> dict[str, Any]:
        needle = str(query or "").strip()
        if not needle:
            raise ValueError("Search query is empty.")
        base = self._resolve(path)
        if not base.is_dir():
            base = base.parent
        limit = max(1, min(120, int(limit)))
        lowered = needle.lower()
        results: list[dict[str, Any]] = []

        for root, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = [
                name
                for name in dirs
                if name not in _SKIP_DIRS and not (Path(root) / name).is_symlink()
            ]
            for filename in files:
                if len(results) >= limit:
                    break
                file_path = Path(root) / filename
                if file_path.is_symlink() or file_path.suffix.lower() in _SKIP_SUFFIXES:
                    continue
                try:
                    safe_file = self._allowed(file_path)
                    if safe_file.stat().st_size > 1_000_000:
                        continue
                    with safe_file.open("r", encoding="utf-8", errors="replace") as handle:
                        for line_no, line in enumerate(handle, 1):
                            if lowered in line.lower():
                                results.append({
                                    "path": str(safe_file),
                                    "line": line_no,
                                    "text": line.rstrip()[:500],
                                })
                                if len(results) >= limit:
                                    break
                except (OSError, ValueError):
                    continue
            if len(results) >= limit:
                break
        return {"base": str(base), "query": needle, "results": results, "truncated": len(results) >= limit}

    def _git_root(self, path: str | None = None) -> Path:
        base = self._resolve(path)
        if base.is_file():
            base = base.parent
        probe = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(base), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env=self._git_env(),
        )
        if probe.returncode != 0:
            raise ValueError("Path is not inside a Git repository.")
        return self._allowed(Path(probe.stdout.strip()))

    def git_status(self, path: str | None = None) -> dict[str, Any]:
        root = self._git_root(path)
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(root), "status", "--short", "--branch"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            env=self._git_env(),
        )
        return {"root": str(root), "status": result.stdout[:12000], "ok": result.returncode == 0}

    def git_diff(self, path: str | None = None, staged: bool = False, max_chars: int = 24000) -> dict[str, Any]:
        root = self._git_root(path)
        command = [
            "git", "-c", "core.fsmonitor=false", "-C", str(root),
            "diff", "--no-ext-diff", "--no-textconv",
        ]
        if staged:
            command.append("--cached")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=self._git_env(),
        )
        diff = result.stdout
        truncated = len(diff) > max_chars
        if truncated:
            diff = diff[:max_chars] + "\n…"
        return {
            "root": str(root),
            "diff": diff,
            "staged": staged,
            "truncated": truncated,
            "ok": result.returncode == 0,
        }
