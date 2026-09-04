import asyncio
import importlib.util
import shutil
import sys
import uuid
from pathlib import Path


async def _run_process(
    args: list[str],
    *,
    input_bytes: bytes | None = None,
    timeout_seconds: int = 240,
) -> tuple[bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if input_bytes is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(input_bytes),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError(f"Process timed out: {args[0]}") from None

    if process.returncode != 0:
        message = stderr.decode("utf-8", errors="replace").strip()
        if len(message) > 4000:
            message = message[-4000:]
        raise RuntimeError(f"{args[0]} failed with exit code {process.returncode}: {message}")

    return stdout, stderr


class WhisperCppProvider:
    def __init__(
        self,
        cli_path: Path,
        model_path: Path,
        audio_dir: Path,
        ffmpeg_bin: str = "ffmpeg",
        language: str = "auto",
        no_gpu: bool = False,
    ) -> None:
        self.cli_path = cli_path.expanduser().resolve()
        self.model_path = model_path.expanduser().resolve()
        self.audio_dir = audio_dir.expanduser().resolve()
        self.ffmpeg_bin = ffmpeg_bin
        self.language = language
        self.no_gpu = no_gpu

    @property
    def configured(self) -> bool:
        return (
            self.cli_path.is_file()
            and self.model_path.is_file()
            and shutil.which(self.ffmpeg_bin) is not None
        )

    async def health(self) -> bool:
        return self.configured

    async def transcribe(
        self,
        audio: bytes,
        *,
        suffix: str = ".audio",
        language: str | None = None,
    ) -> dict[str, str]:
        if not self.configured:
            raise RuntimeError(
                "Speech-to-text is not configured. Check MURN_WHISPER_CLI, "
                "MURN_WHISPER_MODEL and ffmpeg."
            )
        if not audio:
            raise ValueError("Audio upload is empty.")

        work_dir = self.audio_dir / "work"
        work_dir.mkdir(parents=True, exist_ok=True)
        job_id = uuid.uuid4().hex

        clean_suffix = suffix.lower() if suffix and len(suffix) <= 12 else ".audio"
        # Keep the uploaded source and ffmpeg-normalized WAV as distinct files even
        # when the upload itself is already a .wav file.
        source_path = work_dir / f"{job_id}-source{clean_suffix}"
        wav_path = work_dir / f"{job_id}-16k.wav"
        output_prefix = work_dir / f"{job_id}-transcript"
        transcript_path = Path(f"{output_prefix}.txt")
        source_path.write_bytes(audio)

        try:
            await _run_process(
                [
                    self.ffmpeg_bin,
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source_path),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(wav_path),
                ]
            )

            selected_language = (language or self.language or "auto").strip() or "auto"
            command = [
                str(self.cli_path),
                "-m",
                str(self.model_path),
                "-f",
                str(wav_path),
                "--output-txt",
                "-of",
                str(output_prefix),
                "-l",
                selected_language,
                "-np",
                "-nt",
            ]
            if self.no_gpu:
                command.append("-ng")

            await _run_process(command)
            if not transcript_path.exists():
                raise RuntimeError("whisper.cpp finished without creating a transcript file.")

            text = transcript_path.read_text(encoding="utf-8").strip()
            if not text:
                raise RuntimeError("whisper.cpp returned an empty transcription.")

            return {
                "text": text,
                "language": selected_language,
                "model": self.model_path.name,
            }
        finally:
            for path in (source_path, wav_path, transcript_path):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass


class PiperTTSProvider:
    def __init__(self, model_path: Path, audio_dir: Path) -> None:
        self.model_path = model_path.expanduser().resolve()
        self.audio_dir = audio_dir.expanduser().resolve()

    @property
    def configured(self) -> bool:
        return self.model_path.is_file() and importlib.util.find_spec("piper") is not None

    async def health(self) -> bool:
        return self.configured

    @property
    def output_dir(self) -> Path:
        path = self.audio_dir / "generated"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def synthesize(self, text: str) -> Path:
        if not self.configured:
            raise RuntimeError(
                "Text-to-speech is not configured. Install the piper-tts package and set "
                "MURN_PIPER_MODEL to a downloaded voice model."
            )

        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Text for speech synthesis cannot be empty.")

        output_path = self.output_dir / f"{uuid.uuid4().hex}.wav"
        await _run_process(
            [
                sys.executable,
                "-m",
                "piper",
                "-m",
                str(self.model_path),
                "-f",
                str(output_path),
                "--",
                clean_text,
            ]
        )

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("Piper finished without creating an audio file.")
        return output_path

    def get_output(self, filename: str) -> Path | None:
        if Path(filename).name != filename or not filename.endswith(".wav"):
            return None
        path = (self.output_dir / filename).resolve()
        if self.output_dir not in path.parents or not path.is_file():
            return None
        return path
