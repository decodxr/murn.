from __future__ import annotations

import argparse
import io
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from array import array
from collections import deque
from pathlib import Path
from typing import Any

import httpx


DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_BLOCK_MS = 30


def _load_sounddevice():
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "The continuous voice client needs sounddevice. Install the voice extra with "
            "`python -m pip install -e '.[voice]'` and install PortAudio on Arch with "
            "`sudo pacman -S portaudio`."
        ) from exc
    return sd


def _rms(block: bytes) -> float:
    samples = array("h")
    samples.frombytes(block)
    if not samples:
        return 0.0
    mean_square = sum(sample * sample for sample in samples) / len(samples)
    return math.sqrt(mean_square)


def _as_device(value: str | None) -> int | str | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _wav_bytes(frames: list[bytes], sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"".join(frames))
    return buffer.getvalue()


def _calibrate(
    *,
    sample_rate: int,
    block_ms: int,
    seconds: float,
    device: int | str | None,
) -> float:
    sd = _load_sounddevice()
    block_size = max(1, int(sample_rate * block_ms / 1000))
    blocks = max(1, int(seconds * 1000 / block_ms))
    levels: list[float] = []

    print(f"Calibrating microphone for {seconds:.1f}s — stay quiet...")
    with sd.RawInputStream(
        samplerate=sample_rate,
        blocksize=block_size,
        device=device,
        channels=1,
        dtype="int16",
    ) as stream:
        for _ in range(blocks):
            data, _overflowed = stream.read(block_size)
            levels.append(_rms(bytes(data)))

    levels.sort()
    median = levels[len(levels) // 2] if levels else 0.0
    return max(300.0, median * 3.0)


def _record_utterance(
    *,
    sample_rate: int,
    block_ms: int,
    threshold: float,
    silence_ms: int,
    max_seconds: float,
    device: int | str | None,
) -> bytes:
    sd = _load_sounddevice()
    block_size = max(1, int(sample_rate * block_ms / 1000))
    pre_roll_blocks = max(1, int(360 / block_ms))
    start_blocks = max(1, int(90 / block_ms))
    silence_blocks_needed = max(1, int(silence_ms / block_ms))
    minimum_speech_blocks = max(1, int(300 / block_ms))
    maximum_blocks = max(1, int(max_seconds * 1000 / block_ms))

    pre_roll: deque[bytes] = deque(maxlen=pre_roll_blocks)
    frames: list[bytes] = []
    consecutive_loud = 0
    consecutive_silent = 0
    speech_blocks = 0
    started = False

    print("🎙️  Listening...  (Ctrl+C to stop)")
    with sd.RawInputStream(
        samplerate=sample_rate,
        blocksize=block_size,
        device=device,
        channels=1,
        dtype="int16",
    ) as stream:
        while True:
            data, overflowed = stream.read(block_size)
            if overflowed:
                print("⚠ microphone overflow", file=sys.stderr)
            block = bytes(data)
            level = _rms(block)

            if not started:
                pre_roll.append(block)
                if level >= threshold:
                    consecutive_loud += 1
                else:
                    consecutive_loud = 0

                if consecutive_loud >= start_blocks:
                    started = True
                    frames.extend(pre_roll)
                    speech_blocks = consecutive_loud
                    print("🗣️  Speaking...")
                continue

            frames.append(block)
            speech_blocks += 1

            if level < threshold * 0.70:
                consecutive_silent += 1
            else:
                consecutive_silent = 0

            if (
                speech_blocks >= minimum_speech_blocks
                and consecutive_silent >= silence_blocks_needed
            ):
                break

            if speech_blocks >= maximum_blocks:
                print("⏱️  Maximum utterance length reached.")
                break

    return _wav_bytes(frames, sample_rate)


def _player_command(path: Path) -> list[str]:
    if shutil.which("pw-play"):
        return ["pw-play", str(path)]
    if shutil.which("aplay"):
        return ["aplay", str(path)]
    if shutil.which("ffplay"):
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
    raise RuntimeError("No audio player found. Install PipeWire pw-play, aplay, or ffplay.")


def _play_wav(audio: bytes) -> None:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
        temp.write(audio)
        path = Path(temp.name)
    try:
        subprocess.run(_player_command(path), check=True)
    finally:
        path.unlink(missing_ok=True)


def _check_backend(client: httpx.Client) -> dict[str, Any]:
    response = client.get("/health")
    response.raise_for_status()
    health = response.json()
    if not health.get("stt"):
        raise RuntimeError("murn. reports STT as unavailable.")
    if not health.get("tts"):
        raise RuntimeError("murn. reports TTS as unavailable.")
    return health


def _run(args: argparse.Namespace) -> None:
    sd = _load_sounddevice()

    if args.list_devices:
        print(sd.query_devices())
        return

    device = _as_device(args.device)
    threshold = args.threshold
    if threshold is None:
        threshold = _calibrate(
            sample_rate=args.sample_rate,
            block_ms=args.block_ms,
            seconds=args.calibration_seconds,
            device=device,
        )

    print(f"Voice threshold: {threshold:.0f} RMS")

    timeout = httpx.Timeout(args.timeout)
    session_id = args.session_id
    base_url = args.url.rstrip("/")

    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        health = _check_backend(client)
        print(
            f"Connected to murn. — model={health.get('model')} "
            f"STT={'OK' if health.get('stt') else 'OFF'} "
            f"TTS={'OK' if health.get('tts') else 'OFF'}"
        )

        while True:
            audio = _record_utterance(
                sample_rate=args.sample_rate,
                block_ms=args.block_ms,
                threshold=threshold,
                silence_ms=args.silence_ms,
                max_seconds=args.max_seconds,
                device=device,
            )

            form: dict[str, str] = {"language": args.language}
            if session_id:
                form["session_id"] = session_id

            print("🧠  Thinking...")
            response = client.post(
                "/v1/voice/chat",
                files={"file": ("speech.wav", audio, "audio/wav")},
                data=form,
            )
            response.raise_for_status()
            result = response.json()

            session_id = str(result["session_id"])
            transcript = str(result.get("transcript") or "")
            message = str(result.get("message") or "")
            print(f"\nYou:   {transcript}")
            print(f"murn.: {message}\n")

            audio_url = str(result.get("audio_url") or "")
            if audio_url:
                audio_response = client.get(audio_url)
                audio_response.raise_for_status()
                print("🔊  Speaking...")
                _play_wav(audio_response.content)

            if args.once:
                break


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Continuous microphone client for murn.")
    parser.add_argument("--url", default="http://127.0.0.1:7331", help="murn. API URL")
    parser.add_argument("--language", default="pt", help="whisper.cpp language, e.g. pt or auto")
    parser.add_argument("--session-id", default=None, help="reuse an existing murn. session")
    parser.add_argument("--device", default=None, help="PortAudio input device index or name")
    parser.add_argument("--list-devices", action="store_true", help="list microphone devices and exit")
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--block-ms", type=int, default=DEFAULT_BLOCK_MS)
    parser.add_argument("--silence-ms", type=int, default=900, help="silence that ends an utterance")
    parser.add_argument("--max-seconds", type=float, default=30.0, help="maximum utterance length")
    parser.add_argument("--calibration-seconds", type=float, default=1.2)
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="manual RMS speech threshold; skips microphone calibration",
    )
    parser.add_argument("--timeout", type=float, default=360.0, help="HTTP request timeout")
    parser.add_argument("--once", action="store_true", help="process one utterance and exit")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        _run(args)
    except KeyboardInterrupt:
        print("\nVoice mode stopped.")
    except (RuntimeError, httpx.HTTPError) as exc:
        print(f"murn voice error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
