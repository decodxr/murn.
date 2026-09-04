import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from murn.agent import Agent
from murn.config import settings
from murn.memory.obsidian import ObsidianMemory
from murn.memory.semantic import SemanticMemory
from murn.providers.comfyui import ComfyUIProvider
from murn.providers.embeddings import OllamaEmbeddingProvider
from murn.providers.ollama import OllamaProvider
from murn.providers.speech import PiperTTSProvider, WhisperCppProvider
from murn.schemas import (
    ChatRequest,
    ChatResponse,
    ImageGenerateRequest,
    SessionCreateRequest,
    SpeechRequest,
)
from murn.sessions import SessionStore
from murn.tools.registry import ToolRegistry

UI_DIR = Path(__file__).parent / "ui"

app = FastAPI(title="murn.", version="0.5.1")
app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

llm = OllamaProvider(settings.ollama_url, settings.ollama_model)
embedding_provider = OllamaEmbeddingProvider(settings.ollama_url, settings.embedding_model)
memory = ObsidianMemory(settings.obsidian_vault, settings.obsidian_memory_dir)
semantic_memory = SemanticMemory(
    settings.obsidian_vault,
    settings.semantic_db,
    embedding_provider,
)
images = ComfyUIProvider(
    settings.comfyui_url,
    settings.comfy_workflow_path,
    settings.comfy_positive_node,
    settings.comfy_negative_node,
    settings.comfy_seed_node,
    settings.comfy_latent_node,
)
stt = WhisperCppProvider(
    settings.whisper_cli,
    settings.whisper_model,
    settings.audio_dir,
    settings.ffmpeg_bin,
    settings.whisper_language,
    settings.whisper_no_gpu,
)
tts = PiperTTSProvider(settings.piper_model, settings.audio_dir)
sessions = SessionStore(settings.session_db)
tools = ToolRegistry(memory, semantic_memory, images)
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


async def _chat_once(request: ChatRequest) -> ChatResponse:
    session_id, history = _session_for(request)
    sessions.append(session_id, "user", request.message)

    try:
        answer = await agent.run(request.message, history)
        sessions.append(session_id, "assistant", answer)
        return ChatResponse(message=answer, model=settings.ollama_model, session_id=session_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _read_audio_upload(file: UploadFile) -> tuple[bytes, str]:
    max_bytes = settings.audio_max_mb * 1024 * 1024
    audio = await file.read(max_bytes + 1)
    if len(audio) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file is larger than {settings.audio_max_mb} MB.",
        )
    if not audio:
        raise HTTPException(status_code=400, detail="Audio upload is empty.")

    suffix = Path(file.filename or "").suffix.lower()
    if not suffix or len(suffix) > 12:
        suffix = ".audio"
    return audio, suffix


@app.get("/", include_in_schema=False)
async def desktop_ui():
    return FileResponse(UI_DIR / "desktop" / "index.html")


@app.get("/mobile", include_in_schema=False)
@app.get("/mobile/", include_in_schema=False)
async def mobile_ui():
    return FileResponse(UI_DIR / "mobile" / "index.html")


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "murn": True,
        "model": settings.ollama_model,
        "ollama": await llm.health(),
        "embedding_model": settings.embedding_model,
        "embeddings": await embedding_provider.health(),
        "comfyui": await images.health(),
        "comfyui_configured": images.configured,
        "stt": await stt.health(),
        "tts": await tts.health(),
        "whisper_model": str(settings.whisper_model),
        "piper_model": str(settings.piper_model),
        "obsidian_vault": str(settings.obsidian_vault),
        "session_db": str(settings.session_db),
        "semantic_db": str(settings.semantic_db),
        "ui": True,
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
    return await _chat_once(request)


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


@app.post("/v1/memory/reindex")
async def memory_reindex():
    try:
        return await semantic_memory.reindex()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/v1/memory/search")
async def memory_search(q: str = Query(min_length=1), limit: int = Query(5, ge=1, le=10)):
    try:
        return {"mode": "semantic", "results": await semantic_memory.search(q, limit)}
    except Exception as exc:
        return {
            "mode": "keyword-fallback",
            "semantic_error": str(exc),
            "results": memory.search(q, limit),
        }


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


@app.get("/v1/images/view")
async def view_generated_image(
    filename: str = Query(min_length=1),
    subfolder: str = Query(default=""),
    image_type: str = Query(default="output", alias="type"),
):
    try:
        content, media_type = await images.fetch_image(filename, subfolder, image_type)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=86400"},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image fetch failed: {exc}") from exc


@app.post("/v1/audio/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
):
    if not stt.configured:
        raise HTTPException(status_code=503, detail="Speech-to-text is not configured.")

    audio, suffix = await _read_audio_upload(file)
    try:
        return await stt.transcribe(audio, suffix=suffix, language=language)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/audio/speech")
async def text_to_speech(request: SpeechRequest):
    if not tts.configured:
        raise HTTPException(status_code=503, detail="Text-to-speech is not configured.")

    try:
        output_path = await tts.synthesize(request.text)
        return FileResponse(output_path, media_type="audio/wav", filename=output_path.name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/v1/audio/files/{filename}")
async def get_generated_audio(filename: str):
    output_path = tts.get_output(filename)
    if output_path is None:
        raise HTTPException(status_code=404, detail="Audio file not found.")
    return FileResponse(output_path, media_type="audio/wav", filename=output_path.name)


@app.post("/v1/voice/chat")
async def voice_chat(
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    language: str | None = Form(default=None),
):
    if not stt.configured:
        raise HTTPException(status_code=503, detail="Speech-to-text is not configured.")
    if not tts.configured:
        raise HTTPException(status_code=503, detail="Text-to-speech is not configured.")

    audio, suffix = await _read_audio_upload(file)
    try:
        transcription = await stt.transcribe(audio, suffix=suffix, language=language)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"STT failed: {exc}") from exc

    response = await _chat_once(
        ChatRequest(message=transcription["text"], session_id=session_id)
    )

    try:
        output_path = await tts.synthesize(response.message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TTS failed: {exc}") from exc

    return {
        "transcript": transcription["text"],
        "message": response.message,
        "model": response.model,
        "session_id": response.session_id,
        "audio_url": f"/v1/audio/files/{output_path.name}",
    }


@app.post("/v1/voice/remote")
async def voice_remote(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
):
    """Voice-only phone companion. It intentionally does not create a saved chat session."""
    if not stt.configured:
        raise HTTPException(status_code=503, detail="Speech-to-text is not configured.")
    if not tts.configured:
        raise HTTPException(status_code=503, detail="Text-to-speech is not configured.")

    audio, suffix = await _read_audio_upload(file)
    try:
        transcription = await stt.transcribe(audio, suffix=suffix, language=language)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"STT failed: {exc}") from exc

    try:
        answer = await agent.run(transcription["text"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent failed: {exc}") from exc

    try:
        output_path = await tts.synthesize(answer)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TTS failed: {exc}") from exc

    return {
        "transcript": transcription["text"],
        "message": answer,
        "model": settings.ollama_model,
        "ephemeral": True,
        "audio_url": f"/v1/audio/files/{output_path.name}",
    }
