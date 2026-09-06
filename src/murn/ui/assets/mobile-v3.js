(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const els = {
    shell: $('#mobile-shell'),
    title: $('#mobile-state-title'),
    subtitle: $('#mobile-state-subtitle'),
    orb: $('#voice-orb'),
    modeAssistant: $('#mode-assistant'),
    modeVoice: $('#mode-voice'),
    quickActions: $$('.mobile-quick-action'),
    assistantConversation: $('#assistant-conversation'),
    assistantTranscript: $('#assistant-transcript'),
    assistantEmpty: $('#assistant-empty'),
    assistantNewChat: $('#assistant-new-chat'),
    assistantComposer: $('#assistant-composer'),
    assistantInput: $('#assistant-input'),
    assistantIntent: $('#assistant-intent'),
    assistantMic: $('#assistant-mic'),
    assistantSend: $('#assistant-send'),
    tap: $('#tap-to-talk'),
    auto: $('#auto-listen'),
    canvas: $('#wave-canvas'),
    error: $('#mobile-error'),
    connection: $('#phone-connection'),
    techline: $('#phone-techline'),
    desktopIp: $('#desktop-ip'),
  };

  if (!els.shell || !els.canvas) return;
  const ctx = els.canvas.getContext('2d', { alpha: true });

  const STORAGE = {
    mode: 'murn:mobile-mode',
    intent: 'murn:mobile-intent',
    session: 'murn:mobile-assistant-session',
    transcript: 'murn:mobile-assistant-transcript-v1',
  };

  const state = {
    health: null,
    mode: localStorage.getItem(STORAGE.mode) === 'voice' ? 'voice' : 'assistant',
    intent: localStorage.getItem(STORAGE.intent) || 'ask',
    voiceState: 'standby',
    assistantSessionId: localStorage.getItem(STORAGE.session) || null,
    transcript: loadTranscript(),
    stream: null,
    audioContext: null,
    micAnalyser: null,
    micData: null,
    outputAnalyser: null,
    outputData: null,
    playbackSource: null,
    recorder: null,
    chunks: [],
    manual: false,
    manualStarting: false,
    holdSource: null,
    recordMode: null,
    autoEnabled: false,
    busy: false,
    threshold: 0.035,
    calibration: [],
    speechFrames: 0,
    silenceStarted: 0,
    recordingStarted: 0,
    processingTimer: null,
    drawPhase: 0,
    lastDraw: 0,
    renderFrame: 0,
  };

  const voiceLabels = {
    standby: ['STANDBY', 'ready when you are'],
    listening: ['LISTENING', 'capturing your voice'],
    transcribing: ['TRANSCRIBING', 'turning speech into text'],
    thinking: ['THINKING', 'murn. is processing locally'],
    speaking: ['SPEAKING', 'murn. is talking'],
  };

  const assistantLabels = {
    standby: ['READY', 'type or hold the mic to talk'],
    listening: ['LISTENING', 'keep holding while you speak'],
    transcribing: ['HEARD YOU', 'turning speech into text'],
    thinking: ['THINKING', 'working on it locally'],
    speaking: ['SPEAKING', 'murn. is answering'],
  };

  const intentLabels = {
    ask: ['ASK', 'Ask murn...'],
    create: ['CREATE', 'Describe what murn. should create...'],
    code: ['CODE', 'Tell murn. what to build...'],
    plan: ['PLAN', 'What should murn. plan...'],
  };

  function loadTranscript() {
    try {
      const value = JSON.parse(localStorage.getItem(STORAGE.transcript) || '[]');
      return Array.isArray(value) ? value.slice(-40) : [];
    } catch (_) {
      return [];
    }
  }

  function saveTranscript() {
    state.transcript = state.transcript.slice(-40);
    try {
      localStorage.setItem(STORAGE.transcript, JSON.stringify(state.transcript));
    } catch (_) {}
  }

  function clockTime() {
    return new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(new Date());
  }

  function showError(message) {
    els.error.textContent = message;
    els.error.classList.add('show');
    clearTimeout(showError.timer);
    showError.timer = setTimeout(() => els.error.classList.remove('show'), 5500);
  }

  function setVoiceState(name, detail = null) {
    state.voiceState = name;
    els.shell.dataset.state = name;
    els.orb.dataset.state = name;

    const labels = state.mode === 'assistant' ? assistantLabels : voiceLabels;
    const [title, fallback] = labels[name] || labels.standby;
    els.title.textContent = title;
    els.subtitle.textContent = detail || fallback;

    $$('.voice-state-step').forEach((step) => {
      step.classList.toggle('active', step.dataset.state === name);
    });
  }

  function setMode(mode, persist = true) {
    if (!['assistant', 'voice'].includes(mode)) return;
    state.mode = mode;
    els.shell.dataset.mode = mode;
    els.modeAssistant.setAttribute('aria-pressed', String(mode === 'assistant'));
    els.modeVoice.setAttribute('aria-pressed', String(mode === 'voice'));
    if (persist) localStorage.setItem(STORAGE.mode, mode);

    if (mode === 'assistant' && state.autoEnabled) disableAuto();
    setVoiceState(state.voiceState === 'listening' && !state.manual ? 'standby' : state.voiceState);
  }

  function selectIntent(intent) {
    if (!intentLabels[intent]) intent = 'ask';
    state.intent = intent;
    localStorage.setItem(STORAGE.intent, intent);
    els.quickActions.forEach((button) => {
      button.classList.toggle('active', button.dataset.intent === intent);
    });
    const [label, placeholder] = intentLabels[intent];
    els.assistantIntent.textContent = label;
    els.assistantInput.placeholder = placeholder;
  }

  function intentPrompt(text) {
    const clean = String(text || '').trim();
    if (state.intent === 'create') return `Crie uma imagem com este pedido: ${clean}`;
    if (state.intent === 'code') return `Me ajude a programar/construir isto: ${clean}`;
    if (state.intent === 'plan') return `Planeje isto de forma prática: ${clean}`;
    return clean;
  }

  function scrollTranscript() {
    requestAnimationFrame(() => {
      els.assistantTranscript.scrollTop = els.assistantTranscript.scrollHeight;
    });
  }

  function imageUrl(image) {
    if (!image) return '';
    if (typeof image === 'string') return image;
    return String(image.url || '');
  }

  function buildTurn(role, text = '', options = {}) {
    els.assistantEmpty?.remove();
    const turn = document.createElement('article');
    turn.className = `assistant-turn ${role === 'assistant' ? 'murn' : 'user'}`;

    const head = document.createElement('div');
    head.className = 'assistant-turn-head';
    const roleEl = document.createElement('span');
    roleEl.className = 'assistant-turn-role';
    roleEl.textContent = role === 'assistant' ? 'murn.' : 'YOU';
    const time = document.createElement('span');
    time.className = 'assistant-turn-time';
    time.textContent = options.time || clockTime();
    head.append(roleEl, time);

    const bubble = document.createElement('div');
    bubble.className = `assistant-bubble${options.streaming ? ' streaming' : ''}`;
    bubble.textContent = text;

    turn.append(head, bubble);
    els.assistantTranscript.appendChild(turn);

    const images = (options.images || []).map(imageUrl).filter(Boolean);
    if (images.length) appendImages(turn, images);
    scrollTranscript();
    return { turn, bubble, time: time.textContent };
  }

  function appendImages(turn, images) {
    const urls = (images || []).map(imageUrl).filter(Boolean);
    if (!urls.length) return;
    let grid = $('.assistant-images', turn);
    if (!grid) {
      grid = document.createElement('div');
      grid.className = 'assistant-images';
      turn.appendChild(grid);
    }
    for (const url of urls) {
      if ($(`img[src="${CSS.escape(url)}"]`, grid)) continue;
      const img = document.createElement('img');
      img.className = 'assistant-generated-image';
      img.loading = 'lazy';
      img.alt = 'image generated by murn.';
      img.src = url;
      grid.appendChild(img);
    }
    scrollTranscript();
  }

  function appendToolNote(turn, text) {
    let note = $('.assistant-tool-note', turn);
    if (!note) {
      note = document.createElement('div');
      note.className = 'assistant-tool-note';
      turn.appendChild(note);
    }
    note.textContent = text;
    scrollTranscript();
    return note;
  }

  function persistTurn(role, text, images = [], time = null) {
    state.transcript.push({
      role,
      text: String(text || ''),
      images: (images || []).map(imageUrl).filter(Boolean),
      time: time || clockTime(),
    });
    saveTranscript();
  }

  function renderTranscript() {
    els.assistantTranscript.innerHTML = '';
    if (!state.transcript.length) {
      const empty = document.createElement('div');
      empty.className = 'assistant-empty';
      empty.id = 'assistant-empty';
      empty.innerHTML = '<span class="assistant-empty-mark">m<span>.</span></span><p>fala ou escreve alguma coisa.<br />a conversa aparece aqui.</p>';
      els.assistantTranscript.appendChild(empty);
      return;
    }
    for (const item of state.transcript) {
      buildTurn(item.role, item.text, { time: item.time, images: item.images });
    }
  }

  function newAssistantChat() {
    if (state.busy) return;
    state.assistantSessionId = null;
    state.transcript = [];
    localStorage.removeItem(STORAGE.session);
    localStorage.removeItem(STORAGE.transcript);
    renderTranscript();
    setVoiceState('standby');
    els.assistantInput.focus();
  }

  function scheduleBubble(bubble, text) {
    bubble._pendingText = text;
    if (bubble._frame) return;
    bubble._frame = requestAnimationFrame(() => {
      bubble._frame = 0;
      bubble.textContent = bubble._pendingText || '';
      scrollTranscript();
    });
  }

  async function openAssistantStream(message) {
    const payload = { message };
    if (state.assistantSessionId) payload.session_id = state.assistantSessionId;
    let response = await fetch('/v1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (response.status === 404 && state.assistantSessionId) {
      state.assistantSessionId = null;
      localStorage.removeItem(STORAGE.session);
      response = await fetch('/v1/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
    }
    return response;
  }

  function toolStatus(name) {
    if (name === 'generate_image') return 'creating image locally…';
    if (name === 'web_search') return 'searching the web…';
    if (name === 'web_open') return 'reading source…';
    if (name.startsWith('browser_')) return 'using Orbital…';
    if (name.includes('memory')) return 'checking memory…';
    return 'using local tool…';
  }

  async function sendAssistantMessage(displayText, options = {}) {
    const text = String(displayText || '').trim();
    if (!text || state.busy) return;

    state.busy = true;
    els.assistantSend.disabled = true;
    els.assistantMic.disabled = true;

    const userTurn = buildTurn('user', text);
    persistTurn('user', text, [], userTurn.time);
    els.assistantInput.value = '';
    autoGrowAssistantInput();

    const assistant = buildTurn('assistant', '', { streaming: true });
    const generatedImages = [];
    let finalText = '';
    let toolNote = null;
    setVoiceState('thinking');

    try {
      const response = await openAssistantStream(intentPrompt(text));
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
            state.assistantSessionId = event.session_id;
            localStorage.setItem(STORAGE.session, event.session_id);
          } else if (event.type === 'token') {
            finalText += event.content || '';
            scheduleBubble(assistant.bubble, finalText);
          } else if (event.type === 'tool_start') {
            const status = toolStatus(event.name || 'tool');
            setVoiceState('thinking', status);
            toolNote = appendToolNote(assistant.turn, status);
          } else if (event.type === 'tool_result') {
            if (event.name === 'generate_image') {
              const urls = (event.result?.images || []).map(imageUrl).filter(Boolean);
              generatedImages.push(...urls);
              appendImages(assistant.turn, urls);
            }
            if (toolNote) toolNote.textContent = event.result?.ok === false ? 'tool failed' : 'done';
          } else if (event.type === 'done') {
            finalText = event.content ?? finalText;
            scheduleBubble(assistant.bubble, finalText);
          } else if (event.type === 'error') {
            throw new Error(event.error || 'stream error');
          }
        }
      }

      if (assistant.bubble._frame) cancelAnimationFrame(assistant.bubble._frame);
      assistant.bubble._frame = 0;
      assistant.bubble.textContent = finalText || 'done.';
      assistant.bubble.classList.remove('streaming');
      if (toolNote?.textContent === 'done') setTimeout(() => toolNote.remove(), 900);
      persistTurn('assistant', finalText || 'done.', generatedImages, assistant.time);

      if (options.speak && finalText) {
        await speakAssistantText(finalText);
      } else {
        state.busy = false;
        setVoiceState('standby');
      }
    } catch (error) {
      assistant.bubble.classList.remove('streaming');
      assistant.bubble.textContent = `error: ${error.message}`;
      state.busy = false;
      setVoiceState('standby');
      showError(error.message);
    } finally {
      if (!options.speak || !state.busy) {
        els.assistantSend.disabled = false;
        els.assistantMic.disabled = false;
      }
      scrollTranscript();
    }
  }

  function supportedMimeType() {
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
    ];
    return candidates.find((type) => window.MediaRecorder?.isTypeSupported(type)) || '';
  }

  async function health() {
    try {
      const response = await fetch('/health', { cache: 'no-store' });
      if (!response.ok) throw new Error('backend offline');
      state.health = await response.json();
      els.connection.textContent = 'CONNECTED TO PC';
      const model = String(state.health.model || 'llama').replace(':8b', '');
      els.techline.textContent = `LOCAL / ${model.toUpperCase()} / VOICE`;
    } catch (_) {
      els.connection.textContent = 'PC OFFLINE';
    }
  }

  function analyserRms(analyser, data) {
    if (!analyser || !data) return 0;
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) {
      const normalized = (data[i] - 128) / 128;
      sum += normalized * normalized;
    }
    return Math.sqrt(sum / data.length);
  }

  function micRms() {
    return analyserRms(state.micAnalyser, state.micData);
  }

  function visualSource() {
    if (state.voiceState === 'speaking' && state.outputAnalyser && state.outputData) {
      return [state.outputAnalyser, state.outputData];
    }
    return [state.micAnalyser, state.micData];
  }

  async function ensureAudio() {
    if (state.stream && state.audioContext && state.micAnalyser) {
      if (state.audioContext.state === 'suspended') await state.audioContext.resume();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname)) {
        throw new Error('O microfone exige HTTPS no celular.');
      }
      throw new Error('Este navegador não disponibiliza captura de microfone.');
    }

    state.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const AudioContext = window.AudioContext || window.webkitAudioContext;
    state.audioContext = new AudioContext();
    await state.audioContext.resume();
    state.micAnalyser = state.audioContext.createAnalyser();
    state.micAnalyser.fftSize = 1024;
    state.micAnalyser.smoothingTimeConstant = 0.72;
    state.micData = new Uint8Array(state.micAnalyser.fftSize);
    const source = state.audioContext.createMediaStreamSource(state.stream);
    source.connect(state.micAnalyser);
  }

  function buildRecorder(onStop) {
    state.chunks = [];
    const mimeType = supportedMimeType();
    const recorder = new MediaRecorder(state.stream, mimeType ? { mimeType } : undefined);
    state.recorder = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data.size) state.chunks.push(event.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(state.chunks, { type: recorder.mimeType || 'audio/webm' });
      state.recorder = null;
      onStop(blob);
    };
    return recorder;
  }

  function markHoldControls(active) {
    els.tap.classList.toggle('active', active);
    els.assistantMic.classList.toggle('active', active);
  }

  async function startManual(button) {
    if (state.busy || state.manual || state.manualStarting) return;
    if (state.autoEnabled) disableAuto();

    state.manualStarting = true;
    state.holdSource = button;
    state.recordMode = state.mode;
    try {
      await ensureAudio();
      if (state.holdSource !== button) return;
      state.manual = true;
      markHoldControls(true);
      setVoiceState('listening');

      const modeAtStart = state.recordMode;
      const recorder = buildRecorder(async (blob) => {
        state.manual = false;
        state.recordMode = null;
        markHoldControls(false);
        if (blob.size <= 900) {
          setVoiceState('standby');
          return;
        }
        if (modeAtStart === 'assistant') await sendAssistantVoice(blob);
        else await sendRemoteVoice(blob);
      });
      recorder.start();
    } catch (error) {
      state.manual = false;
      state.holdSource = null;
      state.recordMode = null;
      markHoldControls(false);
      showError(error.message);
    } finally {
      state.manualStarting = false;
    }
  }

  function stopManual(button = null) {
    if (!button || state.holdSource === button) state.holdSource = null;
    if (!state.manual || !state.recorder || state.recorder.state !== 'recording') return;
    state.recorder.stop();
  }

  async function transcribeBlob(blob) {
    const form = new FormData();
    const extension = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm';
    form.append('file', blob, `voice.${extension}`);
    form.append('language', 'pt');
    const response = await fetch('/v1/audio/transcribe', { method: 'POST', body: form });
    if (!response.ok) {
      let detail = `transcription failed: ${response.status}`;
      try { detail = (await response.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    return response.json();
  }

  async function sendAssistantVoice(blob) {
    if (state.busy) return;
    state.busy = true;
    els.assistantSend.disabled = true;
    els.assistantMic.disabled = true;
    setVoiceState('transcribing');
    try {
      const transcription = await transcribeBlob(blob);
      const text = String(transcription.text || '').trim();
      state.busy = false;
      els.assistantSend.disabled = false;
      els.assistantMic.disabled = false;
      if (!text) {
        setVoiceState('standby');
        return;
      }
      await sendAssistantMessage(text, { speak: true });
    } catch (error) {
      state.busy = false;
      els.assistantSend.disabled = false;
      els.assistantMic.disabled = false;
      setVoiceState('standby');
      showError(error.message);
    }
  }

  async function calibrate() {
    state.calibration = [];
    const started = performance.now();
    while (performance.now() - started < 850) {
      state.calibration.push(micRms());
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    const sorted = [...state.calibration].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)] || 0.01;
    state.threshold = Math.max(0.025, Math.min(0.11, median * 3.2));
  }

  async function enableAuto() {
    if (state.autoEnabled || state.busy || state.mode !== 'voice') return;
    try {
      await ensureAudio();
      state.autoEnabled = true;
      els.auto.classList.add('active');
      setVoiceState('listening', 'calibrating room noise...');
      await calibrate();
      setVoiceState('listening', 'hands free · just speak');
      autoTick();
    } catch (error) {
      state.autoEnabled = false;
      els.auto.classList.remove('active');
      showError(error.message);
    }
  }

  function disableAuto() {
    state.autoEnabled = false;
    els.auto.classList.remove('active');
    state.speechFrames = 0;
    state.silenceStarted = 0;
    if (state.recorder?.state === 'recording' && !state.manual) state.recorder.stop();
    if (!state.busy) setVoiceState('standby');
  }

  function autoTick() {
    if (!state.autoEnabled) return;
    requestAnimationFrame(autoTick);
    if (state.busy || state.manual || !state.micAnalyser) return;

    const level = micRms();
    const now = performance.now();
    if (!state.recorder) {
      if (level >= state.threshold) state.speechFrames += 1;
      else state.speechFrames = Math.max(0, state.speechFrames - 1);

      if (state.speechFrames >= 4) {
        state.speechFrames = 0;
        state.silenceStarted = 0;
        state.recordingStarted = now;
        const recorder = buildRecorder(async (blob) => {
          if (blob.size > 900) await sendRemoteVoice(blob);
          else if (state.autoEnabled) setVoiceState('listening', 'hands free · just speak');
        });
        recorder.start();
        setVoiceState('listening', 'capturing your voice...');
      }
      return;
    }

    if (state.recorder.state !== 'recording') return;
    if (level < state.threshold * .68) {
      if (!state.silenceStarted) state.silenceStarted = now;
    } else {
      state.silenceStarted = 0;
    }

    const recordedFor = now - state.recordingStarted;
    const silentFor = state.silenceStarted ? now - state.silenceStarted : 0;
    if ((recordedFor > 550 && silentFor > 950) || recordedFor > 20000) state.recorder.stop();
  }

  async function sendRemoteVoice(blob) {
    if (state.busy) return;
    state.busy = true;
    setVoiceState('transcribing');
    clearTimeout(state.processingTimer);
    state.processingTimer = setTimeout(() => {
      if (state.busy) setVoiceState('thinking');
    }, 850);

    try {
      const form = new FormData();
      const extension = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm';
      form.append('file', blob, `voice.${extension}`);
      form.append('language', 'pt');
      const response = await fetch('/v1/voice/remote', { method: 'POST', body: form });
      if (!response.ok) {
        let detail = `voice request failed: ${response.status}`;
        try { detail = (await response.json()).detail || detail; } catch (_) {}
        throw new Error(detail);
      }
      const result = await response.json();
      clearTimeout(state.processingTimer);
      const heard = String(result.transcript || '').trim();
      setVoiceState('thinking', heard ? `“${heard.slice(0, 58)}${heard.length > 58 ? '…' : ''}”` : null);
      if (result.audio_url) await playResponseUrl(result.audio_url);
      else finishPlaybackState();
    } catch (error) {
      clearTimeout(state.processingTimer);
      finishPlaybackState();
      showError(error.message);
    }
  }

  async function speakAssistantText(text) {
    try {
      const response = await fetch('/v1/audio/speech', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) throw new Error(`speech failed: ${response.status}`);
      const buffer = await response.arrayBuffer();
      await playAudioBuffer(buffer);
    } catch (error) {
      state.busy = false;
      els.assistantSend.disabled = false;
      els.assistantMic.disabled = false;
      setVoiceState('standby');
      showError(error.message);
    }
  }

  async function playResponseUrl(url) {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error('failed to download voice response');
    await playAudioBuffer(await response.arrayBuffer());
  }

  async function playAudioBuffer(buffer) {
    await ensureAudio();
    const decoded = await state.audioContext.decodeAudioData(buffer.slice(0));
    const source = state.audioContext.createBufferSource();
    const analyser = state.audioContext.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = .78;
    source.buffer = decoded;
    source.connect(analyser);
    analyser.connect(state.audioContext.destination);
    state.playbackSource = source;
    state.outputAnalyser = analyser;
    state.outputData = new Uint8Array(analyser.fftSize);
    source.onended = finishPlaybackState;
    setVoiceState('speaking');
    source.start();
  }

  function finishPlaybackState() {
    state.playbackSource = null;
    state.outputAnalyser = null;
    state.outputData = null;
    state.busy = false;
    els.assistantSend.disabled = false;
    els.assistantMic.disabled = false;
    setVoiceState(state.mode === 'voice' && state.autoEnabled ? 'listening' : 'standby');
  }

  function getVisualSamples() {
    const [analyser, data] = visualSource();
    if (!analyser || !data) return { data: null, level: 0 };
    return { data, level: analyserRms(analyser, data) };
  }

  function drawWave(timestamp = 0) {
    requestAnimationFrame(drawWave);
    if (timestamp - state.lastDraw < 30) return;
    state.lastDraw = timestamp;

    const width = els.canvas.width;
    const height = els.canvas.height;
    ctx.clearRect(0, 0, width, height);
    state.drawPhase += .04;

    const visual = getVisualSamples();
    const busyFloor = ['transcribing', 'thinking'].includes(state.voiceState) ? .18 : 0;
    const speakingFloor = state.voiceState === 'speaking' ? .14 : 0;
    const listeningFloor = state.voiceState === 'listening' ? .08 : 0;
    const intensity = Math.min(1, visual.level * 11 + busyFloor + speakingFloor + listeningFloor + .045);
    const centerY = height * .5;

    const gradient = ctx.createLinearGradient(0, 0, width, 0);
    gradient.addColorStop(0, 'rgba(155,118,255,0)');
    gradient.addColorStop(.16, 'rgba(165,145,223,.32)');
    gradient.addColorStop(.48, 'rgba(229,226,239,.92)');
    gradient.addColorStop(.54, 'rgba(188,168,239,.88)');
    gradient.addColorStop(.84, 'rgba(165,145,223,.32)');
    gradient.addColorStop(1, 'rgba(155,118,255,0)');

    const sampleAt = (t) => {
      if (!visual.data) return Math.sin(t * 16 + state.drawPhase) * .075;
      const index = Math.min(visual.data.length - 1, Math.floor(t * visual.data.length));
      return (visual.data[index] - 128) / 128;
    };

    for (let layer = 0; layer < 6; layer += 1) {
      ctx.beginPath();
      ctx.lineWidth = layer === 0 ? 3 : 1;
      ctx.strokeStyle = layer === 0 ? gradient : `rgba(174,160,207,${Math.max(.035, .16 - layer * .022)})`;
      ctx.shadowBlur = layer === 0 ? 15 : 4;
      ctx.shadowColor = 'rgba(155,118,255,.42)';
      const phase = state.drawPhase * (1 + layer * .055) + layer * .8;
      const amplitude = 38 + intensity * 150 + layer * 7;
      for (let x = 0; x <= width; x += 5) {
        const t = x / width;
        const envelope = Math.sin(Math.PI * t) ** 1.25;
        const source = sampleAt(t);
        const ribbon = Math.sin(t * (13 + layer * 1.7) + phase) * (.12 + intensity * .10);
        const secondary = Math.sin(t * 27 - phase * .75) * (.035 + intensity * .025);
        const y = centerY + (source * .72 + ribbon + secondary) * amplitude * envelope;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    ctx.shadowBlur = 0;
    const bars = 78;
    for (let i = 0; i < bars; i += 1) {
      const t = i / (bars - 1);
      const envelope = Math.sin(Math.PI * t) ** 1.8;
      const source = Math.abs(sampleAt(t));
      const synthetic = (Math.sin(t * 19 + state.drawPhase * 2.1) + 1) * .5;
      const h = envelope * (22 + intensity * 112) * (.28 + source * 2.4 + synthetic * .25);
      const x = t * width;
      ctx.strokeStyle = `rgba(167,146,221,${.035 + envelope * (.08 + intensity * .08)})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, centerY - h);
      ctx.lineTo(x, centerY + h);
      ctx.stroke();
    }
  }

  function bindHold(button) {
    button.addEventListener('pointerdown', async (event) => {
      event.preventDefault();
      try { button.setPointerCapture(event.pointerId); } catch (_) {}
      await startManual(button);
    });
    const finish = (event) => {
      event?.preventDefault?.();
      stopManual(button);
    };
    button.addEventListener('pointerup', finish);
    button.addEventListener('pointercancel', finish);
    button.addEventListener('lostpointercapture', finish);
    button.addEventListener('contextmenu', (event) => event.preventDefault());
  }

  function autoGrowAssistantInput() {
    els.assistantInput.style.height = 'auto';
    els.assistantInput.style.height = `${Math.min(els.assistantInput.scrollHeight, 92)}px`;
  }

  bindHold(els.tap);
  bindHold(els.assistantMic);

  els.auto.addEventListener('click', async () => {
    if (state.autoEnabled) disableAuto();
    else await enableAuto();
  });

  els.modeAssistant.addEventListener('click', () => setMode('assistant'));
  els.modeVoice.addEventListener('click', () => setMode('voice'));
  els.quickActions.forEach((button) => {
    button.addEventListener('click', () => selectIntent(button.dataset.intent));
  });

  els.assistantNewChat.addEventListener('click', newAssistantChat);
  els.assistantComposer.addEventListener('submit', (event) => {
    event.preventDefault();
    sendAssistantMessage(els.assistantInput.value);
  });
  els.assistantInput.addEventListener('input', autoGrowAssistantInput);
  els.assistantInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendAssistantMessage(els.assistantInput.value);
    }
  });

  async function boot() {
    els.desktopIp.textContent = window.location.host;
    renderTranscript();
    selectIntent(state.intent);
    setMode(state.mode, false);
    setVoiceState('standby');
    await health();
    drawWave();
    setInterval(health, 20000);

    if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname)) {
      showError('Para usar o microfone pelo Wi-Fi, abra o murn. mobile em HTTPS.');
    }
  }

  boot();
})();
