# murn. UI

murn. v0.5 ships two interfaces served directly by the FastAPI backend. There is no Node build step and no cloud dependency.

- **Desktop:** full chat UI with saved conversations, streaming, tool cards, images and voice.
- **Phone:** voice-only companion for the LAN. Phone requests are intentionally ephemeral and do **not** create saved conversations in SQLite.

## Design

The UI follows the black / white / violet murn. visual system:

- matte black background
- thin monochrome borders
- violet as the only strong accent
- large `murn.` wordmark
- mono UI typography
- terminal-inspired labels without pretending to be a literal terminal
- tool activity shown as local operation cards

## 1. Update murn.

```fish
cd ~/Projects/murn
git pull
source .venv/bin/activate.fish
python -m pip install -e '.[voice]'
```

No JavaScript packages need to be installed. The desktop and phone clients are plain local HTML/CSS/JS bundled with murn.

## 2. Desktop UI

Start the backend normally:

```fish
cd ~/Projects/murn
source .venv/bin/activate.fish
uvicorn murn.main:app --reload --host 127.0.0.1 --port 7331
```

Open:

```text
http://127.0.0.1:7331
```

The API docs remain at:

```text
http://127.0.0.1:7331/docs
```

### Desktop features

- saved SQLite conversations in the left sidebar
- open any previous conversation at any time
- search conversations
- right-click a conversation to pin/unpin it locally in the UI
- streaming model text
- visible `memory_search`, `generate_image`, and other tool activity
- generated ComfyUI images displayed in the conversation
- desktop microphone button using the existing `/v1/voice/chat` endpoint
- health/status panel
- mobile companion address in settings

The desktop UI uses the same session database already used by the API:

```text
.murn/sessions.db
```

## 3. Phone voice UI

The phone interface is:

```text
/mobile
```

It has no conversation list and uses:

```text
POST /v1/voice/remote
```

That endpoint performs:

```text
phone microphone
      |
      v
whisper.cpp on PC
      |
      v
murn. agent on PC
      |
      v
Piper on PC
      |
      v
voice response on phone
```

`/v1/voice/remote` does not create a persistent chat session. This keeps phone voice interactions out of the desktop conversation sidebar.

The mobile interface has these visual states:

```text
STANDBY
LISTENING
TRANSCRIBING
THINKING
SPEAKING
```

There are two controls:

- **TAP TO TALK** — hold the button while speaking.
- **AUTO LISTEN** — calibrates room noise, detects voice, waits for silence, sends the utterance, plays murn.'s reply, and starts listening again.

## 4. Quick LAN test without microphone

To expose murn. to the local network:

```fish
uvicorn murn.main:app --reload --host 0.0.0.0 --port 7331
```

Find the PC address:

```fish
hostname -I
```

For example, if the PC is `192.168.1.24`, open on the phone:

```text
http://192.168.1.24:7331/mobile
```

The page and backend status will work over plain HTTP. However, browser microphone access on a phone normally requires a **secure context (HTTPS)**. Use one of the methods below for voice capture.

## 5. Easiest Android development method: ADB reverse

For development, Android can treat the PC service as phone `localhost`, which is allowed to request microphone access without setting up LAN certificates.

Install Android platform tools:

```fish
sudo pacman -S android-tools
```

Enable USB debugging on the phone, connect it by USB, then:

```fish
adb devices
adb reverse tcp:7331 tcp:7331
```

Run murn. on the PC:

```fish
uvicorn murn.main:app --reload --host 127.0.0.1 --port 7331
```

Open on the phone:

```text
http://127.0.0.1:7331/mobile
```

Now the phone page reaches the PC through ADB and browser microphone access can use the trustworthy `localhost` origin.

Remove the reverse tunnel later with:

```fish
adb reverse --remove tcp:7331
```

## 6. Wireless LAN microphone with local HTTPS

For a completely wireless setup, serve murn. over HTTPS on the LAN.

One local-only approach is `mkcert`.

Install it:

```fish
sudo pacman -S mkcert nss
```

Find your LAN IP:

```fish
set MURN_IP (hostname -I | awk '{print $1}')
echo $MURN_IP
```

Create a certificate directory:

```fish
mkdir -p ~/Projects/murn/.murn/certs
cd ~/Projects/murn
```

Install the local CA on the PC and create a certificate containing your LAN IP:

```fish
mkcert -install
mkcert \
  -cert-file .murn/certs/murn.pem \
  -key-file .murn/certs/murn-key.pem \
  $MURN_IP localhost 127.0.0.1 ::1
```

Start murn. with TLS:

```fish
source .venv/bin/activate.fish
uvicorn murn.main:app \
  --host 0.0.0.0 \
  --port 7331 \
  --ssl-certfile .murn/certs/murn.pem \
  --ssl-keyfile .murn/certs/murn-key.pem
```

Open on the phone:

```text
https://YOUR_PC_IP:7331/mobile
```

The phone must trust the mkcert root CA. Find it on the PC with:

```fish
mkcert -CAROOT
```

Copy `rootCA.pem` from that directory to the phone and install it as a trusted user CA. The exact settings menu differs by Android/iOS version. Keep this certificate private; it is your local development CA.

## 7. Firewall

If the phone cannot reach the PC, make sure TCP port `7331` is allowed on your trusted LAN. Do not expose this unauthenticated development server directly to the public internet.

## 8. Desktop voice

The microphone icon in the desktop composer records a short clip in the browser, sends it through the persistent `/v1/voice/chat` endpoint, adds both sides to the current saved conversation, and automatically plays the Piper response.

The standalone terminal voice client still exists:

```fish
murn-voice
```

## 9. Current UI files

```text
src/murn/ui/
├── assets/
│   ├── desktop.js
│   ├── mobile.js
│   └── murn.css
├── desktop/
│   └── index.html
└── mobile/
    └── index.html
```

The backend serves these files from `src/murn/main.py`.

## 10. Useful URLs

```text
Desktop UI       http://127.0.0.1:7331/
Phone UI         http://127.0.0.1:7331/mobile
API docs         http://127.0.0.1:7331/docs
Health           http://127.0.0.1:7331/health
Saved sessions   http://127.0.0.1:7331/v1/sessions
```

## Architecture after v0.5

```text
                         murn. PC

 desktop UI  ───────┐
                    |
                    v
                FastAPI
              /    |     \
         sessions agent   voice
          SQLite   |      /   \
                  tools whisper Piper
                 /   \
            Obsidian ComfyUI

 phone UI ──LAN/HTTPS──> /v1/voice/remote
                             |
                             └── ephemeral: not saved in sessions.db
```
