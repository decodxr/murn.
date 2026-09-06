from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RequestProfile:
    name: str
    temperature: float
    top_p: float
    prompt_path: Path | None = None


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _recent_text(message: str, history: list[dict[str, Any]] | None) -> str:
    bits = [message]
    for item in (history or [])[-5:]:
        bits.append(str(item.get("content") or ""))
    return _norm("\n".join(bits))


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def classify_request(
    message: str,
    history: list[dict[str, Any]] | None = None,
) -> RequestProfile:
    """Choose a lightweight expert profile without another LLM call."""
    text = _recent_text(message, history)

    coding = (
        "```", "traceback", "stack trace", "syntaxerror", "typeerror", "referenceerror",
        "programa", "programar", "programacao", "codigo", "code", "bug", "debug",
        "python", "javascript", "typescript", "rust", "cargo", "tauri", "fastapi",
        "react", "node", "css", "html", "api", "sql", "git", "github", "linux",
        "arch linux", "fish", "bash", "terminal", "shell", "compilar", "build",
        ".py", ".js", ".ts", ".rs", ".tsx", ".jsx", ".css", ".html", ".json",
    )
    language = (
        "reescre", "revis", "corrige esse texto", "corrija esse texto", "gramatica",
        "ortografia", "pontuacao", "traduz", "traducao", "redacao", "frase", "texto",
        "email", "e-mail", "carta", "legenda", "copy", "roteiro", "resumo", "poema",
        "portugues", "ingles", "espanhol", "linguistica", "tom mais", "deixe mais humano",
    )
    factual = (
        "quem criou", "quando aconteceu", "qual empresa", "qual versao", "qual modelo",
        "quantos", "quanto custa", "qual data", "qual ano", "e verdade", "confere",
        "verifica", "fato", "fonte", "noticia", "noticias", "atual", "hoje",
    )

    if _has_any(text, coding):
        return RequestProfile("coding", 0.18, 0.82, Path("prompts/coding.md"))
    if _has_any(text, language):
        return RequestProfile("language", 0.52, 0.92, Path("prompts/language.md"))
    if _has_any(text, factual):
        return RequestProfile("factual", 0.22, 0.82, Path("prompts/reliability.md"))
    return RequestProfile("general", 0.42, 0.90, Path("prompts/reliability.md"))


def load_profile_prompt(profile: RequestProfile) -> str:
    if profile.prompt_path is None:
        return ""
    try:
        return profile.prompt_path.expanduser().read_text(encoding="utf-8").strip()
    except OSError:
        return ""
