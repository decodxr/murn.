# Local voice setup

murn. v0.4.1 uses:

- **whisper.cpp** for local speech-to-text
- **ffmpeg** to normalize uploaded audio to 16 kHz mono PCM WAV
- **Piper** for local text-to-speech
- **sounddevice + PortAudio** for the optional continuous microphone client

The API exposes:

```text
POST /v1/audio/transcribe
POST /v1/audio/speech
GET  /v1/audio/files/{filename}
POST /v1/voice/chat
```

## 1. Install/build whisper.cpp

On Arch Linux:

```fish
sudo pacman -S --needed git cmake base-devel ffmpeg
mkdir -p ~/AI
cd ~/AI
git clone https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
cmake -B build
cmake --build build -j
bash ./models/download-ggml-model.sh base
```

This should create:

```text
~/AI/whisper.cpp/build/bin/whisper-cli
~/AI/whisper.cpp/models/ggml-base.bin
```

The multilingual `base` model is a good first test. You can later switch to `small`, `medium`, or another compatible model by changing `MURN_WHISPER_MODEL`.

## 2. Install Piper and microphone support into the murn. venv

On Arch, install PortAudio for microphone capture:

```fish
sudo pacman -S --needed portaudio
```

From the murn. repository:

```fish
cd ~/Projects/murn
source .venv/bin/activate.fish
python -m pip install -e '.[voice]'
```

Download a Brazilian Portuguese voice:

```fish
mkdir -p ~/.local/share/murn/voices
python -m piper.download_voices \
  --data-dir ~/.local/share/murn/voices \
  pt_BR-faber-medium
```

The expected model is:

```text
~/.local/share/murn/voices/pt_BR-faber-medium.onnx
```

Piper also downloads the matching `.onnx.json` configuration file.

## 3. Configure `.env`

```env
MURN_WHISPER_CLI=/home/you/AI/whisper.cpp/build/bin/whisper-cli
MURN_WHISPER_MODEL=/home/you/AI/whisper.cpp/models/ggml-base.bin
MURN_WHISPER_LANGUAGE=auto
MURN_WHISPER_NO_GPU=false
MURN_FFMPEG_BIN=ffmpeg

MURN_PIPER_MODEL=/home/you/.local/share/murn/voices/pt_BR-faber-medium.onnx
MURN_AUDIO_MAX_MB=25
```

Use your real home directory instead of `/home/you`.

## 4. Check configuration

```fish
python scripts/check_local.py
```

You want:

```text
STT / whisper.cpp: OK
TTS / Piper: OK
```

The `/health` endpoint also exposes `stt` and `tts` booleans.

## 5. Test speech-to-text

Any common browser/audio format is accepted as long as ffmpeg can decode it. murn. converts it to the exact WAV format whisper.cpp expects.

```fish
curl -X POST http://127.0.0.1:7331/v1/audio/transcribe \
  -F 'file=@recording.webm'
```

Force Brazilian Portuguese instead of auto-detection:

```fish
curl -X POST http://127.0.0.1:7331/v1/audio/transcribe \
  -F 'file=@recording.webm' \
  -F 'language=pt'
```

## 6. Test text-to-speech

```fish
curl -X POST http://127.0.0.1:7331/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"text":"Olá. Eu sou o murn."}' \
  --output murn.wav
```

Play it on PipeWire:

```fish
pw-play murn.wav
```

## 7. Full voice chat API

```fish
curl -X POST http://127.0.0.1:7331/v1/voice/chat \
  -F 'file=@recording.webm'
```

The response contains:

```json
{
  "transcript": "what you said",
  "message": "murn.'s answer",
  "model": "llama3.1:8b",
  "session_id": "...",
  "audio_url": "/v1/audio/files/....wav"
}
```

Reuse a session:

```fish
curl -X POST http://127.0.0.1:7331/v1/voice/chat \
  -F 'file=@recording.webm' \
  -F 'session_id=PASTE_SESSION_ID_HERE'
```

Generated voice responses are stored under `.murn/audio/generated/` and `.murn/` is ignored by Git.

## 8. Continuous microphone conversation

Keep the murn. backend running in one terminal:

```fish
cd ~/Projects/murn
source .venv/bin/activate.fish
uvicorn murn.main:app --reload --host 127.0.0.1 --port 7331
```

In another terminal:

```fish
cd ~/Projects/murn
source .venv/bin/activate.fish
murn-voice
```

The client calibrates the microphone for about a second, then loops automatically:

```text
listen -> detect speech -> detect silence -> upload -> murn. -> download WAV -> play -> listen
```

It keeps the `session_id` returned by the first turn, so every spoken turn belongs to the same conversation until the client exits.

Stop it with `Ctrl+C`.

Useful options:

```fish
# List PortAudio input/output devices
murn-voice --list-devices

# Select microphone by index
murn-voice --device 3

# One-turn test
murn-voice --once

# Let Whisper auto-detect the language
murn-voice --language auto

# Wait longer before deciding you finished speaking
murn-voice --silence-ms 1200

# Manually tune voice activity threshold if automatic calibration is poor
murn-voice --threshold 500
```

The client does not listen while murn.'s generated WAV is playing. That prevents the assistant from immediately hearing its own voice and replying to itself.

## Architecture

```text
microphone
   |
   v
local VAD / end-of-speech detection
   |
   v
16 kHz WAV
   |
   v
POST /v1/voice/chat
   |
   +--> ffmpeg -> whisper.cpp -> text
   |                         |
   |                         v
   |                       murn.
   |                  /      |      \
   |               Llama   memory   tools
   |                         |
   |                         v
   +<---------------------- Piper
   |
   v
WAV -> pw-play -> microphone listening resumes
```

The STT, TTS, and microphone client are separate from the agent core, so another local backend can replace any of them later without redesigning sessions, memory, or tools.
