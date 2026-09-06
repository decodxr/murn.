from murn.tool_router import required_tool_names, select_tool_definitions, tool_guidance


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
    "calculate",
    "workspace_roots",
    "workspace_list",
    "workspace_read",
    "workspace_search",
    "workspace_git_status",
    "workspace_git_diff",
    "web_search",
    "web_open",
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
    "generate_image",
)


def _names(message: str, history=None) -> set[str]:
    selected = select_tool_definitions(message, ALL, history)
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
    assert required_tool_names("abre o orbital") == {"browser_launch"}


def test_explicit_web_research_routes_web_only():
    names = _names("pesquisa as noticias de hoje sobre NVIDIA")
    assert {"web_search", "web_open"} <= names
    assert "browser_launch" not in names
    assert required_tool_names("pesquisa as noticias de hoje sobre NVIDIA") == {"web_search"}


def test_image_request_routes_image():
    assert _names("crie uma imagem de uma nave") == {"generate_image"}
    assert required_tool_names("crie uma imagem de uma nave") == {"generate_image"}


def test_image_followup_keeps_generate_image_available_and_required():
    history = [
        {"role": "user", "content": "crie uma imagem sua"},
        {"role": "assistant", "content": "imagem criada"},
    ]
    assert "generate_image" in _names("nn, eu digo do rosto", history)
    assert required_tool_names("nn, eu digo do rosto", history) == {"generate_image"}


def test_browser_followup_requires_only_concrete_action():
    history = [
        {"role": "user", "content": "abre o youtube no orbital"},
        {"role": "assistant", "content": "youtube aberto"},
    ]
    names = _names("clica no primeiro resultado", history)
    assert {"browser_snapshot", "browser_click"} <= names
    assert required_tool_names("clica no primeiro resultado", history) == {"browser_click"}


def test_browser_scroll_followup_requires_scroll_only():
    history = [{"role": "user", "content": "abre esse site no orbital"}]
    assert required_tool_names("rola mais pra baixo", history) == {"browser_scroll"}


def test_workspace_request_routes_read_only_tools():
    names = _names("olha meu projeto e procura esse bug no codigo")
    assert "workspace_read" in names
    assert "workspace_search" in names
    assert "workspace_git_diff" in names
    assert "generate_image" not in names


def test_calculation_routes_deterministic_calculator():
    assert _names("calcula 27 * 19") == {"calculate"}
    assert required_tool_names("calcula 27 * 19") == {"calculate"}


def test_tool_guidance_is_empty_for_simple_chat():
    assert tool_guidance([]) == ""


def test_image_guidance_states_real_generation_capability():
    guidance = tool_guidance(_definitions("generate_image"))
    assert "CONSEGUE" in guidance
    assert "ComfyUI" in guidance
