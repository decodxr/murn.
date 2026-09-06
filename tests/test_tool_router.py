from murn.tool_router import select_tool_definitions, tool_guidance


def _definitions(*names: str):
    return [
        {
            "type": "function",
            "function": {"name": name, "parameters": {"type": "object", "properties": {}}},
        }
        for name in names
    ]


ALL = _definitions(
    "memory_search",
    "memory_write",
    "web_search",
    "web_open",
    "browser_launch",
    "browser_status",
    "browser_snapshot",
    "browser_navigate",
    "browser_click",
    "browser_type",
    "generate_image",
)


def _names(message: str) -> set[str]:
    selected = select_tool_definitions(message, ALL)
    return {item["function"]["name"] for item in selected}


def test_simple_chat_has_no_tools():
    assert _names("fala ae mano") == set()


def test_casual_agora_does_not_trigger_web():
    assert _names("agora eu quero melhorar o app") == set()


def test_orbital_request_routes_browser_family():
    names = _names("abre o orbital")
    assert "browser_launch" in names
    assert "browser_snapshot" in names
    assert "web_search" not in names


def test_explicit_web_research_routes_web_only():
    names = _names("pesquisa as noticias de hoje sobre NVIDIA")
    assert {"web_search", "web_open"} <= names
    assert "browser_launch" not in names


def test_image_request_routes_image():
    assert _names("crie uma imagem de uma nave") == {"generate_image"}


def test_tool_guidance_is_empty_for_simple_chat():
    assert tool_guidance([]) == ""
