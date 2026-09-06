(() => {
  const $ = (selector) => document.querySelector(selector);
  const els = {
    shell: $('#mini-shell'),
    orb: $('#mini-orb'),
    canvas: $('#mini-wave'),
    state: $('#mini-state'),
    detail: $('#mini-detail'),
    talk: $('#mini-talk'),
    auto: $('#mini-auto'),
    expand: $('#mini-expand'),
    pin: $('#mini-pin'),
    lastRole: $('.mini-last-role'),
    lastText: $('.mini-last-text'),
    connection: $('#mini-connection'),
    connectionText: $('#mini-connection-text'),
    model: $('#mini-model'),
    error: $('#mini-error'),
  };
  if (!els.canvas || !els.orb) return;

  const ctx = els.canvas.getContext('2d', { alpha: true });
  const state = {
    sessionId: localStorage.getItem('murn:mini-session') || null,
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
    autoEnabled: false,
    busy: false,
    threshold: .035,
    speechFrames: 0,
    silenceStarted: 0,
    recordingStarted: 0,
    phase: 0,
    lastFrame: 0,
    pinned: true,
  };

  const labels = {
    standby: ['STANDBY', 'ready when you are'],
    listening: ['LISTENING', 'capturing your voice'],
    transcribing: ['TRANSCRIBING', 'turning speech into text'],
    thinking: ['THINKING', 'murn. is processing'],
    speaking: ['SPEAKING', 'murn. is talking'],
  };

  function setStatus(name, detail = null) {
    const [title, fallback] = labels[name] || labels.standby;
    els.shell.dataset.state = name;
    els.orb.dataset.state = name;
    els.state.textContent = title;
    els.detail.textContent = detail || fallback;
  }

  function showError(message) {
    els.error.textContent = String(message || 'unknown error');
    els.error.classList.add('show');
    clearTimeout(showError.timer);
    showError.timer = setTimeout(() => els.error.classList.remove('show'), 4500);
  }

  async function invoke(command, args = {}) {
    const fn = window.__TAURI__?.core?.invoke;
    if (!fn) return null;
    try {
      return await fn(command, args);
    } catch (error) {
      console.warn(`tauri ${command} failed`, error);
      return null;
    }
  }

  async function health() {
    try {
      const response = await fetch('/health', { cache: 'no-store' });
      if (!response.ok) throw new Error('offline');
      const info = await response.json();
      els.connection.classList.add('online');
      els.connectionText.textContent = 'CONNECTED';
      els.model.textContent = String(info.model || 'LOCAL').replace(':8b', '').toUpperCase();
    } catch (_) {
      els.connection.classList.remove('online');
      els.connectionText.textContent = 'OFFLINE';
    }
  }

  function supportedMime() {
    const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
    return types.find((type) => window.MediaRecorder?.isTypeSupported(type)) || '';
  }

  function rms(analyser, data) {
    if (!analyser || !data) return 0;
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) {
      const value = (data[i] - 128) / 128;
      sum += value * value;
    }
    return Math.sqrt(sum / data.length);
  }

  async function ensureAudio() {
    if (state.stream && state.audioContext && state.micAnalyser) {
      if (state.audioContext.state === 'suspended') await state.audioContext.resume();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      throw new Error('microphone capture is unavailable');
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
    state.micAnalyser.smoothingTimeConstant = .72;
    state.micData = new Uint8Array(state.micAnalyser.fftSize);
    const source = state.audioContext.createMediaStreamSource(state.stream);
    source.connect(state.micAnalyser);
  }

  function buildRecorder(onStop) {
    state.chunks = [];
    const mime = supportedMime();
    const recorder = new MediaRecorder(state.stream, mime ? { mimeType: mime } : undefined);
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

  async function startManual() {
    if (state.busy || state.manual || state.manualStarting) return;
    if (state.autoEnabled) disableAuto();
    state.manualStarting = true;
    try {
      await ensureAudio();
      state.manual = true;
      els.talk.classList.add('active');
      setStatus('listening');
      const recorder = buildRecorder(async (blob) => {
        state.manual = false;
        els.talk.classList.remove('active');
        if (blob.size > 900) await sendVoice(blob);
        else setStatus('standby');
      });
      recorder.start();
    } catch (error) {
      state.manual = false;
      els.talk.classList.remove('active');
      setStatus('standby');
      showError(error.message);
    } finally {
      state.manualStarting = false;
    }
  }

  function stopManual() {
    if (!state.manual || !state.recorder || state.recorder.state !== 'recording') return;
    state.recorder.stop();
  }

  async function sendVoice(blob) {
    if (state.busy) return;
    state.busy = true;
    setStatus('transcribing');
    try {
      const form = new FormData();
      const extension = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm';
      form.append('file', blob, `mini.${extension}`);
      form.append('language', 'pt');
      if (state.sessionId) form.append('session_id', state.sessionId);

      const response = await fetch('/v1/voice/chat', { method: 'POST', body: form });
      if (!response.ok) {
        let detail = `voice request failed: ${response.status}`;
        try { detail = (await response.json()).detail || detail; } catch (_) {}
        throw new Error(detail);
      }
      const result = await response.json();
      if (result.session_id) {
        state.sessionId = result.session_id;
        localStorage.setItem('murn:mini-session', result.session_id);
      }
      const heard = String(result.transcript || '').trim();
      if (heard) {
        els.lastRole.textContent = 'YOU';
        els.lastText.textContent = heard;
      }
      setStatus('thinking', heard ? `“${heard.slice(0, 52)}${heard.length > 52 ? '…' : ''}”` : null);

      if (result.message) {
        els.lastRole.textContent = 'murn.';
        els.lastText.textContent = String(result.message).replace(/\s+/g, ' ').trim();
      }
      if (result.audio_url) await playResponse(result.audio_url);
      else finishPlayback();
    } catch (error) {
      state.busy = false;
      setStatus(state.autoEnabled ? 'listening' : 'standby');
      showError(error.message);
    }
  }

  async function playResponse(url) {
    await ensureAudio();
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error('failed to load voice response');
    const buffer = await response.arrayBuffer();
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
    source.onended = finishPlayback;
    setStatus('speaking');
    source.start();
  }

  function finishPlayback() {
    state.playbackSource = null;
    state.outputAnalyser = null;
    state.outputData = null;
    state.busy = false;
    setStatus(state.autoEnabled ? 'listening' : 'standby');
  }

  async function calibrate() {
    const levels = [];
    const started = performance.now();
    while (performance.now() - started < 750) {
      levels.push(rms(state.micAnalyser, state.micData));
      await new Promise((resolve) => setTimeout(resolve, 45));
    }
    levels.sort((a, b) => a - b);
    const median = levels[Math.floor(levels.length / 2)] || .01;
    state.threshold = Math.max(.025, Math.min(.11, median * 3.2));
  }

  async function enableAuto() {
    if (state.autoEnabled || state.busy) return;
    try {
      await ensureAudio();
      state.autoEnabled = true;
      els.auto.setAttribute('aria-pressed', 'true');
      setStatus('listening', 'calibrating room noise…');
      await calibrate();
      setStatus('listening', 'hands free · just speak');
      autoTick();
    } catch (error) {
      state.autoEnabled = false;
      els.auto.setAttribute('aria-pressed', 'false');
      showError(error.message);
    }
  }

  function disableAuto() {
    state.autoEnabled = false;
    els.auto.setAttribute('aria-pressed', 'false');
    state.speechFrames = 0;
    state.silenceStarted = 0;
    if (state.recorder?.state === 'recording' && !state.manual) state.recorder.stop();
    if (!state.busy) setStatus('standby');
  }

  function autoTick() {
    if (!state.autoEnabled) return;
    requestAnimationFrame(autoTick);
    if (state.busy || state.manual || !state.micAnalyser) return;
    const level = rms(state.micAnalyser, state.micData);
    const now = performance.now();

    if (!state.recorder) {
      state.speechFrames = level >= state.threshold
        ? state.speechFrames + 1
        : Math.max(0, state.speechFrames - 1);
      if (state.speechFrames >= 4) {
        state.speechFrames = 0;
        state.silenceStarted = 0;
        state.recordingStarted = now;
        const recorder = buildRecorder(async (blob) => {
          if (blob.size > 900) await sendVoice(blob);
          else if (state.autoEnabled) setStatus('listening', 'hands free · just speak');
        });
        recorder.start();
        setStatus('listening', 'capturing your voice…');
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

  function visualSource() {
    if (els.shell.dataset.state === 'speaking' && state.outputAnalyser) {
      return [state.outputAnalyser, state.outputData];
    }
    return [state.micAnalyser, state.micData];
  }

  function drawWave(timestamp = 0) {
    requestAnimationFrame(drawWave);
    if (timestamp - state.lastFrame < 32) return;
    state.lastFrame = timestamp;
    const width = els.canvas.width;
    const height = els.canvas.height;
    ctx.clearRect(0, 0, width, height);
    state.phase += .045;
    const [analyser, data] = visualSource();
    const level = rms(analyser, data);
    const current = els.shell.dataset.state;
    const floor = current === 'speaking' ? .16 : current === 'thinking' || current === 'transcribing' ? .12 : current === 'listening' ? .07 : .025;
    const intensity = Math.min(1, level * 11 + floor);
    const center = height * .5;
    const gradient = ctx.createLinearGradient(0, 0, width, 0);
    gradient.addColorStop(0, 'rgba(155,118,255,0)');
    gradient.addColorStop(.18, 'rgba(170,158,205,.25)');
    gradient.addColorStop(.5, 'rgba(235,234,240,.9)');
    gradient.addColorStop(.56, 'rgba(185,169,229,.78)');
    gradient.addColorStop(.84, 'rgba(170,158,205,.24)');
    gradient.addColorStop(1, 'rgba(155,118,255,0)');

    const sample = (t) => {
      if (!analyser || !data) return Math.sin(t * 15 + state.phase) * .08;
      analyser.getByteTimeDomainData(data);
      const index = Math.min(data.length - 1, Math.floor(t * data.length));
      return (data[index] - 128) / 128;
    };

    for (let layer = 0; layer < 4; layer += 1) {
      ctx.beginPath();
      ctx.lineWidth = layer === 0 ? 2.7 : 1;
      ctx.strokeStyle = layer === 0 ? gradient : `rgba(185,176,210,${.10 - layer * .018})`;
      ctx.shadowBlur = layer === 0 ? 13 : 3;
      ctx.shadowColor = 'rgba(155,118,255,.32)';
      const amplitude = 28 + intensity * 105 + layer * 6;
      for (let x = 0; x <= width; x += 5) {
        const t = x / width;
        const envelope = Math.sin(Math.PI * t) ** 1.35;
        const ribbon = Math.sin(t * (12 + layer * 1.6) + state.phase + layer) * (.11 + intensity * .08);
        const y = center + (sample(t) * .7 + ribbon) * amplitude * envelope;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    ctx.shadowBlur = 0;
  }

  els.talk.addEventListener('pointerdown', async (event) => {
    event.preventDefault();
    try { els.talk.setPointerCapture(event.pointerId); } catch (_) {}
    await startManual();
  });
  const stop = (event) => { event?.preventDefault?.(); stopManual(); };
  els.talk.addEventListener('pointerup', stop);
  els.talk.addEventListener('pointercancel', stop);
  els.talk.addEventListener('lostpointercapture', stop);
  els.talk.addEventListener('contextmenu', (event) => event.preventDefault());

  els.auto.addEventListener('click', async () => {
    if (state.autoEnabled) disableAuto();
    else await enableAuto();
  });

  els.expand.addEventListener('click', async () => {
    await invoke('set_window_mode', { mode: 'full' });
    location.href = `/?ui=0.14.0&from=mini&t=${Date.now()}`;
  });

  els.pin.addEventListener('click', async () => {
    state.pinned = !state.pinned;
    els.pin.setAttribute('aria-pressed', String(state.pinned));
    await invoke('set_window_pin', { pinned: state.pinned });
  });

  async function boot() {
    setStatus('standby');
    await health();
    await invoke('set_window_pin', { pinned: true });
    drawWave();
    setInterval(health, 20000);
  }

  boot();
})();
