import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from murn.debug import debug_bus
from murn.intelligence import RequestProfile, classify_request, load_profile_prompt
from murn.providers.ollama import OllamaProvider
from murn.tool_router import required_tool_names, select_tool_definitions, tool_guidance
from murn.tools.registry import ToolRegistry


IDENTITY_PROMPT_FALLBACK = """# murn. / identity
Seu nome é murn. Você é uma IA pessoal local-first criada pelo próprio desenvolvedor/usuário deste projeto.
Não atribua sua criação a nenhuma empresa ou pessoa externa. Se não souber um fato sobre sua própria
origem, diga que não tem esse dado em vez de inventar.
"""

SYSTEM_PROMPT_FALLBACK = """Você é murn., uma IA pessoal local.
Fale em português brasileiro natural, direto e com personalidade.
Não soe como chatbot corporativo. Não comece com confirmações genéricas, não repita o pedido e não
termine com frases de atendimento. Seja útil, preciso e honesto sobre ações e ferramentas.
Se não souber um fato, admita a incerteza; nunca preencha lacunas com detalhes inventados.
"""

HISTORY_MAX_MESSAGES = 20
HISTORY_MAX_CHARS = 12000
ORBITAL_CONTEXT_MARKER = "[ORBITAL PAGE CONTEXT"


class Agent:
    def __init__(
        self,
        llm: OllamaProvider,
        tools: ToolRegistry,
        max_steps: int = 8,
        system_prompt_path: Path | None = None,
        identity_prompt_path: Path | None = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.system_prompt_path = system_prompt_path or Path("prompts/system.md")
        self.identity_prompt_path = identity_prompt_path or Path("prompts/identity.md")

    @staticmethod
    def _read_prompt(path: Path, fallback: str) -> str:
        try:
            prompt = path.expanduser().read_text(encoding="utf-8").strip()
        except OSError:
            return fallback
        return prompt or fallback

    def identity_prompt(self) -> str:
        return self._read_prompt(self.identity_prompt_path, IDENTITY_PROMPT_FALLBACK)

    def system_prompt(self) -> str:
        return self._read_prompt(self.system_prompt_path, SYSTEM_PROMPT_FALLBACK)

    @staticmethod
    def _recent_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
        if not history:
            return []
        selected: list[dict[str, str]] = []
        used_chars = 0
        for item in reversed(history[-HISTORY_MAX_MESSAGES:]):
            content = str(item.get("content") or "")
            size = len(content)
            if selected and used_chars + size > HISTORY_MAX_CHARS:
                break
            selected.append(item)
            used_chars += size
            if used_chars >= HISTORY_MAX_CHARS:
                break
        selected.reverse()
        return selected

    @staticmethod
    def _routing_message(message: str) -> str:
        marker = message.find(ORBITAL_CONTEXT_MARKER)
        return message[:marker].strip() if marker >= 0 else message

    @classmethod
    def _routing_history(cls, history: list[dict[str, str]] | None) -> list[dict[str, str]]:
        cleaned: list[dict[str, str]] = []
        for item in history or []:
            cleaned.append(
                {
                    "role": str(item.get("role") or "user"),
                    "content": cls._routing_message(str(item.get("content") or "")),
                }
            )
        return cleaned

    def _messages(
        self,
        message: str,
        history: list[dict[str, str]] | None,
        tool_definitions: list[dict[str, Any]],
        profile: RequestProfile,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.identity_prompt()},
            {"role": "system", "content": self.system_prompt()},
        ]
        profile_prompt = load_profile_prompt(profile)
        if profile_prompt:
            messages.append({"role": "system", "content": profile_prompt})
        guidance = tool_guidance(tool_definitions)
        if guidance:
            messages.append({"role": "system", "content": guidance})
        messages.extend(self._recent_history(history))
        messages.append({"role": "user", "content": message})
        return messages

    @staticmethod
    def _tool_result_for_model(name: str, result: dict[str, Any]) -> dict[str, Any]:
        if name != "generate_image" or not isinstance(result, dict):
            return result
        safe = dict(result)
        safe_images: list[dict[str, Any]] = []
        for image in result.get("images") or []:
            if not isinstance(image, dict):
                continue
            safe_images.append(
                {
                    key: value
                    for key, value in image.items()
                    if key in {"filename", "subfolder", "type"}
                }
            )
        safe["images"] = safe_images
        safe["display"] = "Rendered inline by the murn. client. Do not output a URL."
        return safe

    def _tool_definitions(
        self,
        message: str,
        history: list[dict[str, str]] | None,
    ) -> list[dict[str, Any]]:
        routing_history = self._routing_history(history)
        return select_tool_definitions(
            self._routing_message(message),
            self.tools.definitions(),
            routing_history,
        )

    def _required_tools(
        self,
        message: str,
        history: list[dict[str, str]] | None,
    ) -> set[str]:
        return required_tool_names(self._routing_message(message), self._routing_history(history))

    @staticmethod
    def _tool_names(definitions: list[dict[str, Any]]) -> list[str]:
        return [
            str((definition.get("function") or {}).get("name") or "")
            for definition in definitions
            if (definition.get("function") or {}).get("name")
        ]

    @staticmethod
    def _decision_summary(tool_names: list[str], profile: RequestProfile) -> str:
        names = set(tool_names)
        if "generate_image" in names:
            return "pedido visual/follow-up detectado; geração local de imagem está disponível."
        if any(name.startswith("browser_") for name in names):
            return "pedido ligado ao Orbital; ferramentas do navegador foram liberadas."
        if {"web_search", "web_open"} & names:
            return "pedido externo/atual; pesquisa e leitura da web foram liberadas."
        if any(name.startswith("workspace_") for name in names):
            return "pedido de programação depende do projeto local; workspace read-only foi liberado."
        if "calculate" in names:
            return "há cálculo explícito; calculadora determinística foi liberada."
        if {"memory_search", "memory_write"} & names:
            return "contexto/memória pode mudar a resposta; ferramentas de memória foram liberadas."
        return f"nenhuma ferramenta parece necessária; resposta direta no perfil {profile.name}."

    @staticmethod
    def _context_stats(
        messages: list[dict[str, Any]],
        tool_names: list[str],
        profile: RequestProfile,
        required: set[str],
    ) -> dict[str, Any]:
        chars = 0
        roles: dict[str, int] = {}
        for item in messages:
            role = str(item.get("role") or "unknown")
            roles[role] = roles.get(role, 0) + 1
            chars += len(str(item.get("content") or ""))
        return {
            "messages": len(messages),
            "characters": chars,
            "roles": roles,
            "tools": tool_names,
            "required_tools": sorted(required),
            "profile": profile.name,
            "temperature": profile.temperature,
            "top_p": profile.top_p,
        }

    @staticmethod
    def _ensure_debug_scope(message: str):
        if debug_bus.context().get("trace_id"):
            return None
        _trace_id, token = debug_bus.begin("agent", message)
        return token

    @staticmethod
    def _retry_instruction(missing: set[str]) -> dict[str, str]:
        names = ", ".join(sorted(missing))
        return {
            "role": "system",
            "content": (
                "A solicitação do usuário exige uma ação real e existe ferramenta disponível para isso. "
                f"Você ainda não executou nenhuma das ferramentas necessárias: {names}. "
                "Não responda dizendo que não consegue, não ofereça apenas uma descrição e não invente resultado. "
                "Use agora a ferramenta apropriada."
            ),
        }

    async def _execute_tool(self, name: str, arguments: Any) -> dict[str, Any]:
        if name == "generate_image":
            debug_bus.emit("vram", "unloading llama before image generation")
            await self.llm.unload()
        return await self.tools.execute(name, arguments)

    async def run(self, message: str, history: list[dict[str, str]] | None = None) -> str:
        scope_token = self._ensure_debug_scope(message)
        started = time.perf_counter()
        try:
            routing_history = self._routing_history(history)
            profile = classify_request(self._routing_message(message), routing_history)
            tool_definitions = self._tool_definitions(message, history)
            tool_names = self._tool_names(tool_definitions)
            available = set(tool_names)
            required = self._required_tools(message, history) & available
            used_tools: set[str] = set()
            forced_retry_used = False
            messages = self._messages(message, history, tool_definitions, profile)

            debug_bus.emit("profile", f"request profile: {profile.name}", {
                "temperature": profile.temperature,
                "top_p": profile.top_p,
            })
            debug_bus.emit("router", "tool routing complete", {"enabled": tool_names, "required": sorted(required)})
            debug_bus.emit("decision", self._decision_summary(tool_names, profile))
            debug_bus.emit("context", "model context prepared", self._context_stats(messages, tool_names, profile, required))

            for step in range(1, self.max_steps + 1):
                model_started = time.perf_counter()
                debug_bus.emit("model", "model inference started", {
                    "model": self.llm.model,
                    "step": step,
                    "stream": False,
                    "profile": profile.name,
                })
                assistant = await self.llm.chat(
                    messages,
                    tool_definitions,
                    temperature=profile.temperature,
                    top_p=profile.top_p,
                )
                model_ms = (time.perf_counter() - model_started) * 1000
                tool_calls = assistant.get("tool_calls") or []
                debug_bus.emit("model", "model step finished", {
                    "step": step,
                    "duration_ms": round(model_ms, 1),
                    "tool_calls": [(call.get("function") or {}).get("name") for call in tool_calls],
                    "output_chars": len(str(assistant.get("content") or "")),
                })

                if not tool_calls:
                    missing = required - used_tools
                    if missing and not forced_retry_used:
                        forced_retry_used = True
                        debug_bus.emit("retry", "model ignored required action; forcing one tool retry", {"missing": sorted(missing)})
                        messages.append(self._retry_instruction(missing))
                        continue
                    answer = assistant.get("content", "")
                    debug_bus.emit("done", "response complete", {
                        "total_ms": round((time.perf_counter() - started) * 1000, 1),
                        "output_chars": len(answer),
                        "used_tools": sorted(used_tools),
                    })
                    return answer

                messages.append(assistant)
                for call in tool_calls:
                    function = call.get("function", {})
                    name = str(function.get("name") or "")
                    arguments = function.get("arguments", {})
                    tool_started = time.perf_counter()
                    debug_bus.emit("tool", f"{name} started", {"arguments": arguments})
                    try:
                        result = await self._execute_tool(name, arguments)
                    except Exception as exc:
                        result = {"ok": False, "error": str(exc)}
                    used_tools.add(name)
                    debug_bus.emit("tool", f"{name} finished", {
                        "duration_ms": round((time.perf_counter() - tool_started) * 1000, 1),
                        "result": result,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(self._tool_result_for_model(name, result), ensure_ascii=False),
                    })

            limit = "Atingi o limite de etapas de ferramentas antes de concluir este pedido."
            debug_bus.emit("limit", "agent tool-step limit reached", {"max_steps": self.max_steps})
            return limit
        except Exception as exc:
            debug_bus.emit("error", "agent failed", {"error": str(exc)})
            raise
        finally:
            if scope_token is not None:
                debug_bus.end_scope(scope_token)

    async def stream(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        scope_token = self._ensure_debug_scope(message)
        started = time.perf_counter()
        try:
            routing_history = self._routing_history(history)
            profile = classify_request(self._routing_message(message), routing_history)
            tool_definitions = self._tool_definitions(message, history)
            tool_names = self._tool_names(tool_definitions)
            available = set(tool_names)
            required = self._required_tools(message, history) & available
            used_tools: set[str] = set()
            forced_retry_used = False
            messages = self._messages(message, history, tool_definitions, profile)
            visible_parts: list[str] = []

            debug_bus.emit("profile", f"request profile: {profile.name}", {
                "temperature": profile.temperature,
                "top_p": profile.top_p,
            })
            debug_bus.emit("router", "tool routing complete", {"enabled": tool_names, "required": sorted(required)})
            debug_bus.emit("decision", self._decision_summary(tool_names, profile))
            debug_bus.emit("context", "model context prepared", self._context_stats(messages, tool_names, profile, required))

            for step in range(1, self.max_steps + 1):
                content_parts: list[str] = []
                tool_calls: list[dict[str, Any]] = []
                seen_tool_calls: set[str] = set()
                model_started = time.perf_counter()
                first_token_seen = False
                missing_before = required - used_tools
                buffer_until_action = bool(missing_before)

                debug_bus.emit("model", "model inference started", {
                    "model": self.llm.model,
                    "step": step,
                    "stream": True,
                    "profile": profile.name,
                    "buffer_until_action": buffer_until_action,
                })

                async for chunk in self.llm.stream_chat(
                    messages,
                    tool_definitions,
                    temperature=profile.temperature,
                    top_p=profile.top_p,
                ):
                    assistant_chunk = chunk.get("message") or {}
                    content = assistant_chunk.get("content") or ""
                    if content:
                        if not first_token_seen:
                            first_token_seen = True
                            debug_bus.emit("first_token", "first model token", {
                                "step": step,
                                "latency_ms": round((time.perf_counter() - model_started) * 1000, 1),
                                "buffered": buffer_until_action,
                            })
                        content_parts.append(content)
                        if not buffer_until_action:
                            visible_parts.append(content)
                            yield {"type": "token", "content": content}

                    for call in assistant_chunk.get("tool_calls") or []:
                        key = json.dumps(call, sort_keys=True, ensure_ascii=False)
                        if key not in seen_tool_calls:
                            seen_tool_calls.add(key)
                            tool_calls.append(call)

                assistant: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts)}
                if tool_calls:
                    assistant["tool_calls"] = tool_calls

                debug_bus.emit("model", "model step finished", {
                    "step": step,
                    "duration_ms": round((time.perf_counter() - model_started) * 1000, 1),
                    "tool_calls": [(call.get("function") or {}).get("name") for call in tool_calls],
                    "output_chars": len(assistant["content"]),
                })

                if not tool_calls:
                    missing = required - used_tools
                    if missing and not forced_retry_used:
                        forced_retry_used = True
                        debug_bus.emit("retry", "model ignored required action; hidden text discarded and tool retry forced", {"missing": sorted(missing)})
                        messages.append(self._retry_instruction(missing))
                        continue

                    if buffer_until_action and assistant["content"]:
                        visible_parts.append(assistant["content"])
                        yield {"type": "token", "content": assistant["content"]}
                    final = "".join(visible_parts)
                    debug_bus.emit("done", "response complete", {
                        "total_ms": round((time.perf_counter() - started) * 1000, 1),
                        "output_chars": len(final),
                        "used_tools": sorted(used_tools),
                    })
                    yield {"type": "done", "content": final}
                    return

                messages.append(assistant)
                for call in tool_calls:
                    function = call.get("function", {})
                    name = str(function.get("name") or "")
                    arguments = function.get("arguments", {})
                    yield {"type": "tool_start", "name": name, "arguments": arguments}
                    tool_started = time.perf_counter()
                    debug_bus.emit("tool", f"{name} started", {"arguments": arguments})
                    try:
                        result = await self._execute_tool(name, arguments)
                    except Exception as exc:
                        result = {"ok": False, "error": str(exc)}
                    used_tools.add(name)
                    debug_bus.emit("tool", f"{name} finished", {
                        "duration_ms": round((time.perf_counter() - tool_started) * 1000, 1),
                        "result": result,
                    })
                    yield {"type": "tool_result", "name": name, "result": result}
                    messages.append({
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(self._tool_result_for_model(name, result), ensure_ascii=False),
                    })

            limit_message = "Atingi o limite de etapas de ferramentas antes de concluir este pedido."
            visible_parts.append(limit_message)
            debug_bus.emit("limit", "agent tool-step limit reached", {"max_steps": self.max_steps})
            yield {"type": "token", "content": limit_message}
            yield {"type": "done", "content": "".join(visible_parts)}
        except Exception as exc:
            debug_bus.emit("error", "agent stream failed", {"error": str(exc)})
            raise
        finally:
            if scope_token is not None:
                debug_bus.end_scope(scope_token)
