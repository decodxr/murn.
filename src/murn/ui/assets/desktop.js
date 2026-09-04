(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const state = {
    health: null,
    sessions: [],
    currentSessionId: null,
    sending: false,
    recorder: null,
    recordedChunks: [],
    recordingStream: null,
    toolCounter: 0,
    pendingTools: new Map(),
    pins: new Set(JSON.parse(localStorage.getItem('murn:pins') || '[]')),
  };

  const els = {
    sessionGroups: $('#session-groups'),
    search: $('#session-search'),
    newChat: $('#new-chat'),
    title: $('#conversation-title'),
    meta: $('#conversation-meta'),
    messageList: $('#message-list'),
    welcome: $('#welcome-card'),
    composer: $('#composer'),
    input: $('#message-input'),
    send: $('#send-button'),
    mic: $('#desktop-mic'),
    toast: $('#toast'),
    settings: $('#settings-modal'),
    openSettings: $('#open-settings'),
    mobileUrl: $('#mobile-url'),
    copyMobileUrl: $('#copy-mobile-url'),
  };

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function formatContent(text) {
    const escaped = escapeHtml(text);
    return escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
  }

  function timeNow() {
    return new Intl.DateTimeFormat('pt-BR', {
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date());
  }

  function formatSessionTime(iso) {
    if (!iso) return '';
    const date = new Date(iso);
    const now = new Date();
    const sameDay = date.toDateString() === now.toDateString();
    if (sameDay) {
      return new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(date);
    }
    return new Intl.DateTimeFormat('en-US', { month: 'short', day: '2-digit' }).format(date);
  }

  function groupFor(iso) {
    const date = new Date(iso);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const target = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const days = Math.round((today - target) / 86400000);
    if (days <= 0) return 'today';
    if (days === 1) return 'yesterday';
    return 'older';
  }

  function toast(message) {
    els.toast.textContent = message;
    els.toast.classList.add('show');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => els.toast.classList.remove('show'), 1800);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }
    const type = response.headers.get('content-type') || '';
    return type.includes('application/json') ? response.json() : response;
  }

  async function loadHealth() {
    try {
      const health = await api('/health');
      state.health = health;
      $('#desktop-model').textContent = String(health.model || 'model').replace(':8b', '');
      $('#desktop-local-status').textContent = health.ollama ? 'local' : 'offline';
      $('#desktop-voice').textContent = health.stt && health.tts ? 'voice ready' : 'voice off';
      $('#desktop-connection').textContent = 'connected';
      $('#settings-model').textContent = health.model || '—';
      $('#settings-ollama').textContent = health.ollama ? 'ready' : 'offline';
      $('#settings-comfy').textContent = health.comfyui ? 'ready' : 'offline';
      $('#settings-voice').textContent = health.stt && health.tts ? 'ready' : 'offline';
    } catch (error) {
      $('#desktop-connection').textContent = 'offline';
      $('#desktop-local-status').textContent = 'offline';
      console.error(error);
    }
  }

  async function loadSessions() {
    try {
      const payload = await api('/v1/sessions?limit=200');
      state.sessions = payload.sessions || [];
      renderSessions();
    } catch (error) {
      els.sessionGroups.innerHTML = `<div class="sessions-empty">${escapeHtml(error.message)}</div>`;
    }
  }

  function sessionItem(session, pinned = false) {
    const active = session.id === state.currentSessionId ? ' active' : '';
    const title = session.title || 'New chat';
    const preview = session.message_count ? `${session.message_count} messages` : 'empty conversation';
    return `
      <button class="session-item${active}" data-session-id="${escapeHtml(session.id)}" title="Right-click to ${pinned ? 'unpin' : 'pin'}">
        <span class="session-bubble${pinned ? ' pin-mark' : ''}"></span>
        <span>
          <span class="session-title">${escapeHtml(title)}</span>
          <span class="session-preview">${escapeHtml(preview)}</span>
        </span>
        <span class="session-time">${escapeHtml(formatSessionTime(session.updated_at))}</span>
      </button>`;
  }

  function renderSessions() {
    const filter = els.search.value.trim().toLowerCase();
    const visible = state.sessions.filter((session) => {
      if (!filter) return true;
      return String(session.title || '').toLowerCase().includes(filter);
    });

    const pinned = visible.filter((session) => state.pins.has(session.id));
    const groups = {
      pinned,
      today: visible.filter((s) => !state.pins.has(s.id) && groupFor(s.updated_at) === 'today'),
      yesterday: visible.filter((s) => !state.pins.has(s.id) && groupFor(s.updated_at) === 'yesterday'),
      older: visible.filter((s) => !state.pins.has(s.id) && groupFor(s.updated_at) === 'older'),
    };

    const labels = {
      pinned: ['PINNED', '♟'],
      today: ['TODAY', '▢'],
      yesterday: ['YESTERDAY', '▢'],
      older: ['OLDER', '▢'],
    };

    let html = '';
    for (const key of ['pinned', 'today', 'yesterday', 'older']) {
      if (!groups[key].length) continue;
      html += `<section class="session-group"><h3 class="session-group-title"><span class="group-icon">${labels[key][1]}</span>${labels[key][0]}</h3>`;
      html += groups[key].map((session) => sessionItem(session, key === 'pinned')).join('');
      html += '</section>';
    }

    els.sessionGroups.innerHTML = html || '<div class="sessions-empty">no conversations found.</div>';

    $$('.session-item', els.sessionGroups).forEach((button) => {
      button.addEventListener('click', () => openSession(button.dataset.sessionId));
      button.addEventListener('contextmenu', (event) => {
        event.preventDefault();
        togglePin(button.dataset.sessionId);
      });
    });
  }

  function togglePin(sessionId) {
    if (state.pins.has(sessionId)) state.pins.delete(sessionId);
    else state.pins.add(sessionId);
    localStorage.setItem('murn:pins', JSON.stringify([...state.pins]));
    renderSessions();
    toast(state.pins.has(sessionId) ? 'conversation pinned' : 'conversation unpinned');
  }

  function clearMessages() {
    els.messageList.innerHTML = '';
  }

  function setConversationTitle(title) {
    els.title.textContent = title || 'New Chat';
    els.meta.textContent = 'local · private · persistent';
  }

  function appendMessage(role, content = '', createdAt = null) {
    els.welcome?.remove();
    const wrapper = document.createElement('article');
    wrapper.className = `message ${role === 'assistant' ? 'murn' : 'user'}`;
    wrapper.innerHTML = `
      <div class="avatar ${role === 'assistant' ? 'murn' : 'user'}">${role === 'assistant' ? 'm<span>.</span>' : '&gt;_'}</div>
      <div class="message-body">
        <div class="message-head">
          <span class="message-role">${role === 'assistant' ? 'murn.' : 'YOU'}</span>
          <span class="message-time">${createdAt ? formatSessionTime(createdAt) : timeNow()}</span>
        </div>
        <div class="message-content"></div>
      </div>`;
    const contentEl = $('.message-content', wrapper);
    contentEl.innerHTML = formatContent(content);
    els.messageList.appendChild(wrapper);
    scrollBottom();
    return { wrapper, contentEl, body: $('.message-body', wrapper) };
  }

  function scrollBottom() {
    requestAnimationFrame(() => {
      els.messageList.scrollTop = els.messageList.scrollHeight;
    });
  }

  async function openSession(sessionId) {
    if (!sessionId || state.sending) return;
    try {
      const session = await api(`/v1/sessions/${encodeURIComponent(sessionId)}`);
      state.currentSessionId = session.id;
      setConversationTitle(session.title);
      clearMessages();
      for (const message of session.messages || []) {
        appendMessage(message.role, message.content, message.created_at);
      }
      if (!(session.messages || []).length) {
        els.messageList.innerHTML = '<div class="welcome-card" id="welcome-card"><div class="welcome-mark">m<span>.</span></div><div><h2>new conversation.</h2><p>say something.</p></div></div>';
      }
      renderSessions();
    } catch (error) {
      toast(error.message);
    }
  }

  async function createSession() {
    if (state.sending) return;
    try {
      const session = await api('/v1/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      state.currentSessionId = session.id;
      setConversationTitle('New Chat');
      els.messageList.innerHTML = '<div class="welcome-card" id="welcome-card"><div class="welcome-mark">m<span>.</span></div><div><h2>new conversation.</h2><p>say something.</p></div></div>';
      await loadSessions();
      els.input.focus();
    } catch (error) {
      toast(error.message);
    }
  }

  function summarizeArgs(args) {
    if (!args || typeof args !== 'object') return '';
    const bits = [];
    if (args.query) bits.push(String(args.query).slice(0, 70));
    if (args.prompt) bits.push(String(args.prompt).slice(0, 70));
    if (args.width && args.height) bits.push(`${args.width}x${args.height}`);
    return bits.join(' · ') || 'running locally';
  }

  function toolSymbol(name) {
    if (name.includes('memory')) return '◎';
    if (name.includes('image')) return '▧';
    return '⌁';
  }

  function appendToolStart(messageBody, name, args) {
    let stack = $('.tool-stack', messageBody);
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'tool-stack';
      messageBody.appendChild(stack);
    }
    const id = `tool-${++state.toolCounter}`;
    const card = document.createElement('div');
    card.className = 'tool-card';
    card.dataset.toolId = id;
    card.innerHTML = `
      <span class="tool-icon">${toolSymbol(name)}</span>
      <span><span class="tool-name">${escapeHtml(name)}</span><span class="tool-detail">${escapeHtml(summarizeArgs(args))}</span></span>
      <span class="tool-state"><span class="elapsed">0.0s</span><span class="spinner"></span></span>`;
    card.dataset.started = String(performance.now());
    stack.appendChild(card);
    if (!state.pendingTools.has(name)) state.pendingTools.set(name, []);
    state.pendingTools.get(name).push(card);
    scrollBottom();
    return card;
  }

  function appendGeneratedImages(messageBody, result) {
    const images = result?.images || [];
    for (const image of images) {
      if (!image?.url) continue;
      const img = document.createElement('img');
      img.className = 'generated-image';
      img.alt = image.filename || 'generated image';
      img.loading = 'lazy';
      img.src = image.url;
      messageBody.appendChild(img);
    }
  }

  function resolveTool(messageBody, name, result) {
    const queue = state.pendingTools.get(name) || [];
    const card = queue.shift();
    if (card) {
      const elapsed = (performance.now() - Number(card.dataset.started || performance.now())) / 1000;
      $('.elapsed', card).textContent = `${elapsed.toFixed(1)}s`;
      $('.spinner', card).replaceWith(document.createTextNode('✓'));
      const detail = $('.tool-detail', card);
      if (name === 'memory_search') {
        const count = result?.results?.length ?? 0;
        detail.textContent = `found ${count} relevant ${count === 1 ? 'note' : 'notes'}`;
      } else if (name === 'generate_image') {
        detail.textContent = `comfyui · ${result?.images?.length || 0} image${result?.images?.length === 1 ? '' : 's'} · done`;
      } else {
        detail.textContent = result?.ok === false ? 'failed' : 'done';
      }
    }
    if (name === 'generate_image') appendGeneratedImages(messageBody, result);
    scrollBottom();
  }

  async function sendMessage(text) {
    const message = text.trim();
    if (!message || state.sending) return;

    state.sending = true;
    els.send.disabled = true;
    els.input.value = '';
    autoGrow();
    appendMessage('user', message);
    const assistant = appendMessage('assistant', '');
    assistant.contentEl.classList.add('streaming-cursor');
    let finalText = '';
    state.pendingTools.clear();

    try {
      const payload = { message };
      if (state.currentSessionId) payload.session_id = state.currentSessionId;

      const response = await fetch('/v1/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok || !response.body) throw new Error(`chat failed: ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === 'session') {
            state.currentSessionId = event.session_id;
          } else if (event.type === 'token') {
            finalText += event.content || '';
            assistant.contentEl.innerHTML = formatContent(finalText);
          } else if (event.type === 'tool_start') {
            appendToolStart(assistant.body, event.name || 'tool', event.arguments || {});
          } else if (event.type === 'tool_result') {
            resolveTool(assistant.body, event.name || 'tool', event.result || {});
          } else if (event.type === 'done') {
            finalText = event.content ?? finalText;
            assistant.contentEl.innerHTML = formatContent(finalText);
          } else if (event.type === 'error') {
            throw new Error(event.error || 'stream error');
          }
          scrollBottom();
        }
      }

      assistant.contentEl.classList.remove('streaming-cursor');
      await loadSessions();
      const session = state.sessions.find((item) => item.id === state.currentSessionId);
      if (session) setConversationTitle(session.title);
    } catch (error) {
      assistant.contentEl.classList.remove('streaming-cursor');
      assistant.contentEl.textContent = `error: ${error.message}`;
      toast(error.message);
    } finally {
      state.sending = false;
      els.send.disabled = false;
      els.input.focus();
    }
  }

  function autoGrow() {
    els.input.style.height = 'auto';
    els.input.style.height = `${Math.min(els.input.scrollHeight, 150)}px`;
  }

  function supportedMimeType() {
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
    return candidates.find((type) => window.MediaRecorder?.isTypeSupported(type)) || '';
  }

  async function toggleDesktopMic() {
    if (state.recorder?.state === 'recording') {
      state.recorder.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      toast('browser voice capture is unavailable');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      state.recordingStream = stream;
      state.recordedChunks = [];
      const mimeType = supportedMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      state.recorder = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) state.recordedChunks.push(event.data);
      };
      recorder.onstop = async () => {
        els.mic.classList.remove('recording');
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(state.recordedChunks, { type: recorder.mimeType || 'audio/webm' });
        if (blob.size > 1000) await sendVoice(blob);
      };
      recorder.start();
      els.mic.classList.add('recording');
      toast('listening — click mic again to send');
    } catch (error) {
      toast(error.message);
    }
  }

  async function sendVoice(blob) {
    if (state.sending) return;
    state.sending = true;
    els.send.disabled = true;
    try {
      const form = new FormData();
      form.append('file', blob, 'speech.webm');
      form.append('language', 'pt');
      if (state.currentSessionId) form.append('session_id', state.currentSessionId);
      toast('transcribing / thinking...');
      const result = await api('/v1/voice/chat', { method: 'POST', body: form });
      state.currentSessionId = result.session_id;
      appendMessage('user', result.transcript || '');
      const assistant = appendMessage('assistant', result.message || '');
      const voice = document.createElement('div');
      voice.className = 'voice-card';
      voice.innerHTML = `<span class="tool-icon">◖</span><span><span class="tool-name">voice response</span><span class="tool-detail">piper · pt-BR · local</span></span><span class="wave-mini">${'<i></i>'.repeat(12)}</span>`;
      assistant.body.appendChild(voice);
      if (result.audio_url) {
        const audio = new Audio(result.audio_url);
        await audio.play().catch(() => {});
      }
      await loadSessions();
      const session = state.sessions.find((item) => item.id === state.currentSessionId);
      if (session) setConversationTitle(session.title);
    } catch (error) {
      toast(error.message);
    } finally {
      state.sending = false;
      els.send.disabled = false;
    }
  }

  els.composer.addEventListener('submit', (event) => {
    event.preventDefault();
    sendMessage(els.input.value);
  });

  els.input.addEventListener('input', autoGrow);
  els.input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendMessage(els.input.value);
    }
  });

  els.newChat.addEventListener('click', createSession);
  els.search.addEventListener('input', renderSessions);
  els.mic.addEventListener('click', toggleDesktopMic);

  els.openSettings.addEventListener('click', () => {
    const mobile = `${window.location.protocol}//${window.location.host}/mobile`;
    els.mobileUrl.textContent = mobile;
    els.settings.showModal();
  });

  els.copyMobileUrl.addEventListener('click', async () => {
    await navigator.clipboard.writeText(els.mobileUrl.textContent).catch(() => {});
    toast('mobile address copied');
  });

  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      els.search.focus();
    }
  });

  async function boot() {
    await Promise.all([loadHealth(), loadSessions()]);
    const first = state.sessions[0];
    if (first) await openSession(first.id);
    else await createSession();
  }

  boot();
})();
