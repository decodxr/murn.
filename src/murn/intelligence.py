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


def _history_text(history: list[dict[str, Any]] | None, limit: int = 4) -> str:
    return _norm("\n".join(str(item.get("content") or "") for item in (history or [])[-limit:]))


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


CODING = (
    "```", "traceback", "stack trace", "syntaxerror", "typeerror", "referenceerror",
    "programa", "programar", "programacao", "codigo", "code", "bug", "debug",
    "python", "javascript", "typescript", "rust", "cargo", "tauri", "fastapi",
    "react", "node", "css", "html", "api", "sql", "git", "github", "linux",
    "arch linux", "fish", "bash", "terminal", "shell", "compilar", "build",
    ".py", ".js", ".ts", ".rs", ".tsx", ".jsx", ".css", ".html", ".json",
)
LANGUAGE = (
    "reescre", "revis", "corrige esse texto", "corrija esse texto", "gramatica",
    "ortografia", "pontuacao", "traduz", "traducao", "redacao", "frase", "texto",
    "email", "e-mail", "carta", "legenda", "copy", "roteiro", "resumo", "poema",
    "portugues", "ingles", "espanhol", "linguistica", "tom mais", "deixe mais humano",
)
FACTUAL = (
    "quem criou", "quando aconteceu", "qual empresa", "qual versao", "qual modelo",
    "quantos", "quanto custa", "qual data", "qual ano", "e verdade", "confere",
    "verifica", "fato", "fonte", "noticia", "noticias", "atual", "hoje",
)
FOLLOWUP = (
    "isso", "esse", "essa", "aquele", "aquela", "continua", "continue", "e agora",
    "agora faz", "agora deixa", "desse jeito", "assim", "nessa parte", "neste trecho",
    "aqui", "ai", "da erro", "deu erro", "refaz", "melhora isso",
)


def classify_request(
    message: str,
    history: list[dict[str, Any]] | None = None,
) -> RequestProfile:
    """Choose a lightweight expert profile without another LLM call.

    Current text wins. Recent history only carries a specialist profile across
    short/obvious follow-ups, so a previous coding discussion does not turn
    unrelated small talk into coding mode.
    """
    current = _norm(message)
    previous = _history_text(history)

    if _has_any(current, CODING):
        return RequestProfile("coding", 0.18, 0.82, Path("prompts/coding.md"))
    if _has_any(current, LANGUAGE):
        return RequestProfile("language", 0.52, 0.92, Path("prompts/language.md"))
    if _has_any(current, FACTUAL):
        return RequestProfile("factual", 0.22, 0.82, Path("prompts/reliability.md"))

    is_followup = len(current) <= 90 and _has_any(current, FOLLOWUP)
    if is_followup and _has_any(previous, CODING):
        return RequestProfile("coding", 0.18, 0.82, Path("prompts/coding.md"))
    if is_followup and _has_any(previous, LANGUAGE):
        return RequestProfile("language", 0.52, 0.92, Path("prompts/language.md"))

    return RequestProfile("general", 0.42, 0.90, Path("prompts/reliability.md"))


def load_profile_prompt(profile: RequestProfile) -> str:
    if profile.prompt_path is None:
        return ""
    try:
        return profile.prompt_path.expanduser().read_text(encoding="utf-8").strip()
    except OSError:
        return ""
