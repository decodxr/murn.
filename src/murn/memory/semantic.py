import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from murn.providers.embeddings import OllamaEmbeddingProvider


class SemanticMemory:
    def __init__(
        self,
        vault: Path,
        db_path: Path,
        embeddings: OllamaEmbeddingProvider,
        chunk_chars: int = 1200,
        overlap_chars: int = 180,
    ) -> None:
        self.vault = vault.expanduser().resolve()
        self.db_path = db_path.expanduser().resolve()
        self.embeddings = embeddings
        self.chunk_chars = chunk_chars
        self.overlap_chars = overlap_chars
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    mtime_ns INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    path TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    PRIMARY KEY(path, chunk_index)
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
                """
            )

    @staticmethod
    def _visible_markdown_files(vault: Path) -> list[Path]:
        if not vault.exists():
            return []
        files: list[Path] = []
        for path in vault.rglob("*.md"):
            relative = path.relative_to(vault)
            if any(part.startswith(".") for part in relative.parts):
                continue
            files.append(path)
        return sorted(files)

    def _chunk(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []

        chunks: list[str] = []
        start = 0
        length = len(text)

        while start < length:
            end = min(length, start + self.chunk_chars)
            if end < length:
                paragraph_break = text.rfind("\n\n", start, end)
                line_break = text.rfind("\n", start, end)
                split_at = max(paragraph_break, line_break)
                if split_at > start + self.chunk_chars // 2:
                    end = split_at

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= length:
                break
            start = max(start + 1, end - self.overlap_chars)

        return chunks

    async def reindex(self) -> dict[str, int]:
        files = self._visible_markdown_files(self.vault)
        current_paths = {str(path.relative_to(self.vault)): path for path in files}

        with self._connect() as connection:
            rows = connection.execute("SELECT path, mtime_ns FROM files").fetchall()
            indexed = {row["path"]: int(row["mtime_ns"]) for row in rows}

        removed = set(indexed) - set(current_paths)
        changed: list[tuple[str, Path, int]] = []

        for relative, path in current_paths.items():
            mtime_ns = path.stat().st_mtime_ns
            if indexed.get(relative) != mtime_ns:
                changed.append((relative, path, mtime_ns))

        if removed:
            with self._connect() as connection:
                for relative in removed:
                    connection.execute("DELETE FROM chunks WHERE path = ?", (relative,))
                    connection.execute("DELETE FROM files WHERE path = ?", (relative,))

        chunk_count = 0
        for relative, path, mtime_ns in changed:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            chunks = self._chunk(text)
            vectors = await self.embeddings.embed(chunks) if chunks else []
            if len(vectors) != len(chunks):
                raise RuntimeError(f"Embedding count mismatch while indexing {relative}.")

            with self._connect() as connection:
                connection.execute("DELETE FROM chunks WHERE path = ?", (relative,))
                for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                    connection.execute(
                        "INSERT INTO chunks (path, chunk_index, text, embedding) VALUES (?, ?, ?, ?)",
                        (relative, index, chunk, json.dumps(vector, separators=(",", ":"))),
                    )
                connection.execute(
                    "INSERT OR REPLACE INTO files (path, mtime_ns) VALUES (?, ?)",
                    (relative, mtime_ns),
                )
            chunk_count += len(chunks)

        return {
            "files_total": len(current_paths),
            "files_updated": len(changed),
            "files_removed": len(removed),
            "chunks_updated": chunk_count,
        }

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        await self.reindex()
        query_vector = (await self.embeddings.embed(query))[0]

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT path, chunk_index, text, embedding FROM chunks"
            ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            vector = json.loads(row["embedding"])
            score = self._cosine(query_vector, vector)
            results.append(
                {
                    "path": row["path"],
                    "chunk": int(row["chunk_index"]),
                    "score": round(score, 6),
                    "excerpt": row["text"],
                }
            )

        results.sort(key=lambda item: float(item["score"]), reverse=True)
        return results[:limit]
