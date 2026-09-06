(() => {
  const state = {
    open: false,
    paused: false,
    connected: false,
    eventSource: null,
    seen: new Set(),
    events: [],
    maxEvents: 220,
  };

  function el(tag, className = '', text = '') {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function timeLabel(iso) {
    try {
      return new Intl.DateTimeFormat('pt-BR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }).format(new Date(iso));
    } catch (_) {
      return '--:--:--';
    }
  }

  function pretty(value) {
    try {
      return JSON.stringify(value, null, 2);
    } catch (_) {
      return String(value);
    }
  }

  function normalizeSource(source) {
    const value = String(source || 'agent');
    if (value === 'unknown' || value === 'agent') return 'LOCAL';
    return value.replaceAll('_', ' ').toUpperCase();
  }

  const toggle = el('button', 'murn-debug-toggle');
  toggle.type = 'button';
  toggle.innerHTML = '<span class="debug-live-dot"></span>DEBUG';
  toggle.title = 'debug mode · Ctrl+Shift+D';

  const panel = el('aside', 'murn-debug-panel');
  panel.id = 'murn-debug-panel';
  panel.setAttribute('aria-hidden', 'true');
  panel.innerHTML = `
    <header class="murn-debug-head">
      <div>
        <span class="murn-debug-kicker">MURN / INTERNAL TRACE</span>
        <h2>debug<span>.</span> live</h2>
      </div>
      <div class="murn-debug-head-actions">
        <button class="murn-debug-icon-button" id="murn-debug-pause" type="button">PAUSE</button>
        <button class="murn-debug-icon-button" id="murn-debug-clear" type="button">CLEAR</button>
        <button class="murn-debug-icon-button" id="murn-debug-close" type="button">×</button>
      </div>
    </header>
    <div class="murn-debug-statusbar">
      <span id="murn-debug-live">CONNECTING</span>
      <span>·</span>
      <span>ALL CLIENTS</span>
      <span>·</span>
      <span id="murn-debug-count">0 EVENTS</span>
    </div>
    <div class="murn-debug-feed" id="murn-debug-feed">
      <div class="murn-debug-empty">waiting for murn. activity…<br>ask something from the PC or phone.</div>
    </div>`;

  document.body.appendChild(panel);

  const desktopStrip = document.querySelector('.system-strip');
  const orbital = document.querySelector('#open-orbital');
  const mobileConnection = document.querySelector('.mobile-connection');
  if (desktopStrip) {
    if (orbital) desktopStrip.insertBefore(toggle, orbital);
    else desktopStrip.appendChild(toggle);
  } else if (mobileConnection) {
    mobileConnection.appendChild(toggle);
  } else {
    document.body.appendChild(toggle);
  }

  const feed = panel.querySelector('#murn-debug-feed');
  const live = panel.querySelector('#murn-debug-live');
  const count = panel.querySelector('#murn-debug-count');
  const pause = panel.querySelector('#murn-debug-pause');
  const clear = panel.querySelector('#murn-debug-clear');
  const close = panel.querySelector('#murn-debug-close');

  function syncConnection(connected) {
    state.connected = connected;
    toggle.classList.toggle('connected', connected);
    live.textContent = connected ? 'LIVE' : 'RECONNECTING';
    live.classList.toggle('live', connected);
  }

  function setOpen(open) {
    state.open = Boolean(open);
    panel.classList.toggle('open', state.open);
    panel.setAttribute('aria-hidden', String(!state.open));
    toggle.classList.toggle('active', state.open);
    if (state.open) requestAnimationFrame(() => { feed.scrollTop = feed.scrollHeight; });
  }

  function updateCount() {
    count.textContent = `${state.events.length} ${state.events.length === 1 ? 'EVENT' : 'EVENTS'}`;
  }

  function eventNode(event) {
    const card = el('article', 'murn-debug-event');
    card.dataset.stage = String(event.stage || 'event');

    const meta = el('div', 'murn-debug-meta');
    meta.appendChild(el('span', 'murn-debug-source', normalizeSource(event.source)));
    meta.appendChild(el('span', '', timeLabel(event.ts)));
    meta.appendChild(el('span', 'murn-debug-trace', `#${String(event.trace_id || '').slice(0, 10)}`));
    meta.appendChild(el('span', 'murn-debug-stage', String(event.stage || 'event')));

    const message = el('div', 'murn-debug-message', String(event.message || ''));
    card.append(meta, message);

    if (event.data !== null && event.data !== undefined) {
      const details = el('details', 'murn-debug-data');
      const summary = el('summary', '', 'details');
      const pre = el('pre', '', pretty(event.data));
      details.append(summary, pre);
      card.appendChild(details);
    }
    return card;
  }

  function renderAll() {
    feed.innerHTML = '';
    if (!state.events.length) {
      feed.innerHTML = '<div class="murn-debug-empty">waiting for murn. activity…<br>ask something from the PC or phone.</div>';
      updateCount();
      return;
    }
    const fragment = document.createDocumentFragment();
    for (const event of state.events) fragment.appendChild(eventNode(event));
    feed.appendChild(fragment);
    updateCount();
    if (!state.paused) requestAnimationFrame(() => { feed.scrollTop = feed.scrollHeight; });
  }

  function appendEvent(event) {
    const key = String(event.seq ?? `${event.trace_id}:${event.ts}:${event.stage}:${event.message}`);
    if (state.seen.has(key)) return;
    state.seen.add(key);
    state.events.push(event);
    if (state.events.length > state.maxEvents) {
      const removed = state.events.splice(0, state.events.length - state.maxEvents);
      for (const item of removed) state.seen.delete(String(item.seq));
    }

    if (!feed.querySelector('.murn-debug-empty')) {
      feed.appendChild(eventNode(event));
    } else {
      renderAll();
      return;
    }

    while (feed.children.length > state.maxEvents) feed.firstElementChild?.remove();
    updateCount();
    if (!state.paused) requestAnimationFrame(() => { feed.scrollTop = feed.scrollHeight; });
  }

  async function loadSnapshot() {
    try {
      const response = await fetch('/v1/debug/snapshot?limit=100', { cache: 'no-store' });
      if (!response.ok) return;
      const payload = await response.json();
      state.events = [];
      state.seen.clear();
      for (const event of payload.events || []) {
        const key = String(event.seq);
        state.seen.add(key);
        state.events.push(event);
      }
      renderAll();
    } catch (_) {}
  }

  function connect() {
    state.eventSource?.close();
    const source = new EventSource('/v1/debug/events?backlog=0');
    state.eventSource = source;
    source.onopen = () => syncConnection(true);
    source.onerror = () => syncConnection(false);
    source.onmessage = (message) => {
      try {
        appendEvent(JSON.parse(message.data));
      } catch (_) {}
    };
  }

  toggle.addEventListener('click', () => setOpen(!state.open));
  close.addEventListener('click', () => setOpen(false));
  pause.addEventListener('click', () => {
    state.paused = !state.paused;
    pause.textContent = state.paused ? 'RESUME' : 'PAUSE';
    if (!state.paused) requestAnimationFrame(() => { feed.scrollTop = feed.scrollHeight; });
  });
  clear.addEventListener('click', async () => {
    try {
      await fetch('/v1/debug/events', { method: 'DELETE' });
    } catch (_) {}
    state.events = [];
    state.seen.clear();
    renderAll();
  });

  window.addEventListener('keydown', (event) => {
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'd') {
      event.preventDefault();
      setOpen(!state.open);
    }
    if (event.key === 'Escape' && state.open) setOpen(false);
  });

  loadSnapshot();
  connect();
})();
