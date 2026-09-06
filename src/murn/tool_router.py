from __future__ import annotations

import unicodedata
from typing import Any


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def select_tool_definitions(
    message: str,
    definitions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return only tool schemas that are plausibly useful for this request.

    Large local models pay a noticeable latency cost when every tool schema is
    included in every request. Simple conversation should therefore reach the
    model with no tool schema at all, while explicit web/browser/memory/image
    requests still get the complete tool family they need.
    """

    text = _norm(message)
    names: set[str] = set()

    memory_search = (
        "lembra", "lembrar", "memoria", "memory", "ja falei", "eu disse",
        "antes eu", "ultima vez", "conversa anterior", "historico", "recorda",
        "o que voce sabe sobre mim", "oq vc sabe sobre mim", "sobre mim",
    )
    memory_write = (
        "lembre disso", "lembra disso", "guarda isso", "guarde isso", "salva na memoria",
        "salve na memoria", "memoriza", "remember this",
    )
    web = (
        "pesquisa", "pesquise", "procura", "procure", "buscar na internet", "busca na internet",
        "na web", "internet", "noticias", "noticia", "hoje", "agora", "atual", "atualmente",
        "mais recente", "ultima versao", "latest", "news", "site oficial", "documentacao atual",
        "verifica online", "confere online",
    )
    browser = (
        "orbital", "navegador", "browser", "abre o site", "abra o site", "abre youtube",
        "abra youtube", "abre o youtube", "abra o youtube", "abre github", "abra github",
        "abre google", "abra google", "clica", "clique", "digita", "digite", "aba aberta",
        "aba do", "nessa pagina", "nesta pagina", "pagina aberta", "rola a pagina", "scroll",
        "volta no navegador", "avanca no navegador", "abre uma aba", "abra uma aba",
    )
    image = (
        "gera uma imagem", "gere uma imagem", "cria uma imagem", "crie uma imagem",
        "gerar imagem", "generate image", "desenha", "desenhe", "renderiza", "renderize",
        "comfyui",
    )

    if _has_any(text, memory_search):
        names.add("memory_search")
    if _has_any(text, memory_write):
        names.update({"memory_search", "memory_write"})
    if _has_any(text, web):
        names.update({"web_search", "web_open"})
    if _has_any(text, browser):
        names.update(
            {
                "browser_launch",
                "browser_status",
                "browser_tabs",
                "browser_focus_tab",
                "browser_snapshot",
                "browser_navigate",
                "browser_click",
                "browser_type",
                "browser_press",
                "browser_scroll",
                "browser_back",
                "browser_forward",
            }
        )
    if _has_any(text, image):
        names.add("generate_image")

    # "abre X" should use the browser when X looks like a web destination,
    # while phrases such as "abre o orbital" are already caught above.
    if ("abre " in text or "abra " in text) and _has_any(
        text,
        (".com", ".org", ".net", "http://", "https://", "youtube", "github", "reddit", "google"),
    ):
        names.update(
            {
                "browser_launch",
                "browser_status",
                "browser_tabs",
                "browser_snapshot",
                "browser_navigate",
                "browser_click",
                "browser_type",
                "browser_press",
            }
        )

    if not names:
        return []

    selected: list[dict[str, Any]] = []
    for definition in definitions:
        name = str((definition.get("function") or {}).get("name") or "")
        if name in names:
            selected.append(definition)
    return selected
