from fastapi import FastAPI, HTTPException, Query

from murn.agent import Agent
from murn.config import settings
from murn.memory.obsidian import ObsidianMemory
from murn.providers.comfyui import ComfyUIProvider
from murn.providers.ollama import OllamaProvider
from murn.schemas import ChatRequest, ChatResponse, ImageGenerateRequest
from murn.tools.registry import ToolRegistry

app = FastAPI(title="murn.", version="0.1.0")

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
tools = ToolRegistry(memory, images)
agent = Agent(llm, tools, settings.agent_max_steps)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "murn": True,
        "model": settings.ollama_model,
        "ollama": await llm.health(),
        "comfyui": await images.health(),
        "comfyui_configured": images.configured,
        "obsidian_vault": str(settings.obsidian_vault),
    }


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        history = [item.model_dump() for item in request.history]
        answer = await agent.run(request.message, history)
        return ChatResponse(message=answer, model=settings.ollama_model)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
