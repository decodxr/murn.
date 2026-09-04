import re
from datetime import datetime
from pathlib import Path


class ObsidianMemory:
    def __init__(self, vault: Path, memory_dir: str = "murn") -> None:
        self.vault = vault.expanduser().resolve()
        self.root = (self.vault / memory_dir / "memory").resolve()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def search(self, query: str, limit: int = 5) -> list[dict[str, str | int]]:
        self._ensure_root()
        terms = [term.lower() for term in query.split() if term.strip()]
        if not terms:
            return []

        results: list[dict[str, str | int]] = []
        for path in self.root.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            lower = text.lower()
            score = sum(lower.count(term) for term in terms)
            if score == 0:
                continue

            first_hit = min((lower.find(term) for term in terms if term in lower), default=0)
            start = max(0, first_hit - 180)
            end = min(len(text), first_hit + 520)
            excerpt = text[start:end].strip()
            results.append(
                {
                    "path": str(path.relative_to(self.vault)),
                    "score": score,
                    "excerpt": excerpt,
                }
            )

        results.sort(key=lambda item: int(item["score"]), reverse=True)
        return results[:limit]

    def write(self, title: str, content: str, tags: list[str] | None = None) -> dict[str, str]:
        self._ensure_root()
        now = datetime.now().astimezone()
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.strip()).strip("-").lower() or "memory"
        filename = f"{now:%Y%m%d-%H%M%S}-{slug[:64]}.md"
        path = (self.root / filename).resolve()

        if self.root not in path.parents:
            raise RuntimeError("Refusing to write outside the murn. memory directory.")

        clean_tags = [re.sub(r"[^a-zA-Z0-9_/-]", "", tag) for tag in (tags or [])]
        clean_tags = [tag for tag in clean_tags if tag]
        frontmatter = ["---", "type: murn-memory", f'created: "{now.isoformat()}"']
        if clean_tags:
            frontmatter.append("tags:")
            frontmatter.extend(f"  - {tag}" for tag in clean_tags)
        frontmatter.extend(["---", ""])

        body = "\n".join(frontmatter) + f"# {title.strip()}\n\n{content.strip()}\n"
        path.write_text(body, encoding="utf-8")
        return {"path": str(path.relative_to(self.vault)), "title": title.strip()}
