import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from murn.agent import Agent
from murn.config import settings
from murn.memory.obsidian import ObsidianMemory
from murn.providers.comfyui import ComfyUIProvider
from murn.providers.ollama import OllamaProvider
from murn.schemas import ChatRequest, ChatResponse, ImageGenerateRequest, SessionCreateRequest
from murn.sessions import SessionStore
from murn.tools.registry import ToolRegistry

app = FastAPI(title="murn.", version="0.2.0")

llm = OllamaProvider(settings.ollama_url, settings.ollama_model)
memory = ObsidianMemory(settings.obsidian_vault, settings.obsidian_memory_dir)
images = ComfyUIProvider(
    settings.comfyui_url,
    settings.comfy_workflow_path,
    settings.comfy_positive_node,
    settings.comfy_negative_node,
    settings.comfy_seed_node,
    settings.comfy_latent_node,
)
sessions = SessionStore(settings.session_db)
tools = ToolRegistry(memory, images)
agent = Agent(llm, tools, settings.agent_max_steps)


def _session_for(request: ChatRequest) -> tuple[str, list[dict[str, str]]]:
    if request.session_id:
        try:
            return request.session_id, sessions.history(request.session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    created = sessions.create()
    history = [item.model_dump() for item in request.history]
    return created["id"], history


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "murn": True,
        "model": settings.ollama_model,
        "ollama": await llm.health(),
        "comfyui": await images.health(),
        "comfyui_configured": images.configured,
        "obsidian_vault": str(settings.obsidian_vault),
        "session_db": str(settings.session_db),
    }


@app.post("/v1/sessions")
async def create_session(request: SessionCreateRequest) -> dict[str, str]:
    return sessions.create(request.title)


@app.get("/v1/sessions")
async def list_sessions(limit: int = Query(50, ge=1, le=200)):
    return {"sessions": sessions.list(limit)}


@app.get("/v1/sessions/{session_id}")
async def get_session(session_id: str):
    try:
        return sessions.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/v1/sessions/{session_id}")
async def delete_session(session_id: str):
    if not sessions.delete(session_id):
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} was not found.")
    return {"ok": True}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session_id, history = _session_for(request)
    sessions.append(session_id, "user", request.message)

    try:
        answer = await agent.run(request.message, history)
        sessions.append(session_id, "assistant", answer)
        return ChatResponse(message=answer, model=settings.ollama_model, session_id=session_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    session_id, history = _session_for(request)
    sessions.append(session_id, "user", request.message)

    async def stream():
        final_content = ""
        yield json.dumps({"type": "session", "session_id": session_id}, ensure_ascii=False) + "\n"
        try:
            async for event in agent.stream(request.message, history):
                if event.get("type") == "done":
                    final_content = str(event.get("content") or "")
                yield json.dumps(event, ensure_ascii=False) + "\n"

            sessions.append(session_id, "assistant", final_content)
        except Exception as exc:
            yield json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.get("/v1/memory/search")
async def memory_search(q: str = Query(min_length=1), limit: int = Query(5, ge=1, le=10)):
    return {"results": memory.search(q, limit)}


@app.post("/v1/images/generate")
async def generate_image(request: ImageGenerateRequest):
    if not images.configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "ComfyUI is not configured yet. Export workflows/txt2img_api.json and set "
                "the MURN_COMFY_*_NODE values in .env."
            ),
        )
    try:
        return await images.generate(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            seed=request.seed,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
