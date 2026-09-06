# murn. debug mode

murn. has a shared live debug console available from both the desktop app and the mobile companion.

## What it shows

The console is an observable execution trace, not raw hidden chain-of-thought. It shows the parts that are useful for debugging the agent:

- request origin (`DESKTOP`, `MOBILE`, `DESKTOP VOICE`, `MOBILE VOICE`, etc.)
- request / trace id
- session id when available
- tool routing decision
- a short explicit decision summary
- model context size and role counts
- model and step number
- latency to first visible token
- model-step duration
- tool names, arguments, compact results and timing
- VRAM unload events before image generation
- vision / voice stages
- total response time
- errors and tool-step limit events

The debug console deliberately does not expose a model's private token-by-token chain-of-thought. The `decision` event is a concise, deterministic explanation of the route murn. chose (for example, why web or Orbital tools were enabled).

## Cross-device behavior

Desktop (`7332`) and mobile/LAN (`7331`) are separate FastAPI processes. Debug events are therefore stored in one shared SQLite database:

```text
.murn/debug_events.db
```

Both backends read and write that database in WAL mode, so a debug console open on the desktop can see a request made from the phone, and the phone can see traces created by the desktop.

The database is automatically kept small by retaining only the latest events.

## UI

Desktop: use the `DEBUG` button in the top status strip or press:

```text
Ctrl + Shift + D
```

Mobile: use the small `DEBUG` button under the connection status.

The panel supports:

- `PAUSE` / `RESUME` for autoscroll
- `CLEAR` to clear only debug events
- expandable event details
- live SSE updates from `/v1/debug/events`

Clearing debug events does not delete chats, long-term memory, images or Obsidian notes.

## API

Recent events:

```bash
curl http://127.0.0.1:7332/v1/debug/snapshot?limit=100
```

Live SSE stream:

```bash
curl -N http://127.0.0.1:7332/v1/debug/events?backlog=20
```

Clear traces:

```bash
curl -X DELETE http://127.0.0.1:7332/v1/debug/events
```

The same endpoints also work through the LAN/mobile backend when appropriate.
