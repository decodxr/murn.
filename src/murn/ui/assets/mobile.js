(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const els = {
    title: $('#mobile-state-title'),
    subtitle: $('#mobile-state-subtitle'),
    tap: $('#tap-to-talk'),
    auto: $('#auto-listen'),
    canvas: $('#wave-canvas'),
    error: $('#mobile-error'),
    connection: $('#phone-connection'),
    techline: $('#phone-techline'),
    desktopIp: $('#desktop-ip'),
  };

  const ctx = els.canvas.getContext('2d');

  const state = {
    health: null,
    stream: null,
    audioContext: null,
    analyser: null,
    analyserData: null,
    recorder: null,
    chunks: [],
    manual: false,
    autoEnabled: false,
    busy: false,
    threshold: 0.035,
    calibration: [],
    speechFrames: 0,
    silenceStarted: 0,
    recordingStarted: 0,
    processingTimer: null,
    drawPhase: 0,
  };

  const labels = {
    standby: ['STANDBY', 'ready when you are'],
    listening: ['LISTENING', 'the phone is the mic and the display'],
    transcribing: ['TRANSCRIBING', 'turning speech into text'],
    thinking: ['THINKING', 'murn. is processing locally'],
    speaking: ['SPEAKING', 'response from your PC'],
  };

  function setVoiceState(name, detail = null) {
    const [title, fallback] = labels[name] || labels.standby;
    els.title.textContent = title;
    els.subtitle.textContent = detail || fallback;
    $$('.state-row').forEach((row) => row.classList.toggle('active', row.dataset.state === name));
  }

  function showError(message) {
    els.error.textContent = message;
    els.error.classList.add('show');
    clearTimeout(showError.timer);
    showError.timer = setTimeout(() => els.error.classList.remove('show'), 5500);
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
      const response = await fetch('/health');
      if (!response.ok) throw new Error('backend offline');
      state.health = await response.json();
      els.connection.textContent = 'CONNECTED TO PC';
      const model = String(state.health.model || 'llama').replace(':8b', '');
      els.techline.textContent = `LOCAL / ${model.toUpperCase()} / VOICE`;
    } catch (error) {
      els.connection.textContent = 'PC OFFLINE';
      showError('murn. backend is offline.');
    }
  }

  function rms() {
    if (!state.analyser || !state.analyserData) return 0;
    state.analyser.getByteTimeDomainData(state.analyserData);
    let sum = 0;
    for (let i = 0; i < state.analyserData.length; i++) {
      const normalized = (state.analyserData[i] - 128) / 128;
      sum += normalized * normalized;
    }
    return Math.sqrt(sum / state.analyserData.length);
  }

  async function ensureAudio() {
    if (state.stream && state.audioContext && state.analyser) {
      if (state.audioContext.state === 'suspended') await state.audioContext.resume();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname)) {
        throw new Error('O microfone do navegador exige HTTPS no celular. Veja docs/ui.md para o modo LAN HTTPS.');
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
    state.analyser = state.audioContext.createAnalyser();
    state.analyser.fftSize = 1024;
    state.analyser.smoothingTimeConstant = 0.72;
    state.analyserData = new Uint8Array(state.analyser.fftSize);
    const source = state.audioContext.createMediaStreamSource(state.stream);
    source.connect(state.analyser);
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

  async function startManual() {
    if (state.busy || state.manual) return;
    if (state.autoEnabled) disableAuto();
    try {
      await ensureAudio();
      state.manual = true;
      els.tap.classList.add('active');
      setVoiceState('listening');
      const recorder = buildRecorder(async (blob) => {
        state.manual = false;
        els.tap.classList.remove('active');
        if (blob.size > 900) await sendRemoteVoice(blob);
        else setVoiceState('standby');
      });
      recorder.start();
    } catch (error) {
      state.manual = false;
      els.tap.classList.remove('active');
      showError(error.message);
    }
  }

  function stopManual() {
    if (!state.manual || !state.recorder || state.recorder.state !== 'recording') return;
    state.recorder.stop();
  }

  async function calibrate() {
    state.calibration = [];
    const started = performance.now();
    while (performance.now() - started < 900) {
      state.calibration.push(rms());
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    const sorted = [...state.calibration].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)] || 0.01;
    state.threshold = Math.max(0.025, Math.min(0.11, median * 3.2));
  }

  async function enableAuto() {
    if (state.autoEnabled) return;
    try {
      await ensureAudio();
      state.autoEnabled = true;
      els.auto.classList.add('active');
      setVoiceState('listening', 'calibrating room noise...');
      await calibrate();
      setVoiceState('listening');
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
    if (state.busy || state.manual || !state.analyser) return;

    const level = rms();
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
          else if (state.autoEnabled) setVoiceState('listening');
        });
        recorder.start();
        setVoiceState('listening', 'capturing your voice...');
      }
      return;
    }

    if (state.recorder.state !== 'recording') return;

    if (level < state.threshold * 0.68) {
      if (!state.silenceStarted) state.silenceStarted = now;
    } else {
      state.silenceStarted = 0;
    }

    const recordedFor = now - state.recordingStarted;
    const silentFor = state.silenceStarted ? now - state.silenceStarted : 0;

    if ((recordedFor > 550 && silentFor > 950) || recordedFor > 20000) {
      state.recorder.stop();
    }
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
        try {
          const body = await response.json();
          detail = body.detail || detail;
        } catch (_) {}
        throw new Error(detail);
      }

      const result = await response.json();
      clearTimeout(state.processingTimer);
      setVoiceState('thinking', result.transcript ? `“${result.transcript.slice(0, 64)}${result.transcript.length > 64 ? '…' : ''}”` : null);

      if (result.audio_url) {
        await playResponse(result.audio_url);
      } else {
        state.busy = false;
        setVoiceState(state.autoEnabled ? 'listening' : 'standby');
      }
    } catch (error) {
      clearTimeout(state.processingTimer);
      state.busy = false;
      setVoiceState(state.autoEnabled ? 'listening' : 'standby');
      showError(error.message);
    }
  }

  async function playResponse(url) {
    try {
      await ensureAudio();
      const response = await fetch(url);
      if (!response.ok) throw new Error('failed to download voice response');
      const buffer = await response.arrayBuffer();
      const decoded = await state.audioContext.decodeAudioData(buffer.slice(0));
      const source = state.audioContext.createBufferSource();
      source.buffer = decoded;
      source.connect(state.audioContext.destination);
      source.onended = () => {
        state.busy = false;
        setVoiceState(state.autoEnabled ? 'listening' : 'standby');
      };
      setVoiceState('speaking');
      source.start();
    } catch (error) {
      state.busy = false;
      setVoiceState(state.autoEnabled ? 'listening' : 'standby');
      showError(error.message);
    }
  }

  function drawWave() {
    requestAnimationFrame(drawWave);
    const width = els.canvas.width;
    const height = els.canvas.height;
    ctx.clearRect(0, 0, width, height);

    state.drawPhase += 0.022;
    const activeLevel = rms();
    const intensity = Math.min(1, activeLevel * 9 + (state.busy ? 0.28 : 0.08));
    const centerY = height / 2;
    const gradient = ctx.createLinearGradient(0, 0, width, 0);
    gradient.addColorStop(0, 'rgba(156,108,255,0)');
    gradient.addColorStop(0.2, 'rgba(156,108,255,.9)');
    gradient.addColorStop(0.5, 'rgba(210,185,255,1)');
    gradient.addColorStop(0.8, 'rgba(156,108,255,.9)');
    gradient.addColorStop(1, 'rgba(156,108,255,0)');

    for (let layer = 0; layer < 4; layer++) {
      ctx.beginPath();
      ctx.lineWidth = layer === 0 ? 3.2 : 1.15;
      ctx.strokeStyle = layer === 0 ? gradient : `rgba(156,108,255,${0.32 - layer * 0.055})`;
      ctx.shadowBlur = layer === 0 ? 18 : 7;
      ctx.shadowColor = '#9c6cff';

      const amplitude = 26 + intensity * 135 + layer * 9;
      for (let x = 0; x <= width; x += 4) {
        const t = x / width;
        const envelope = Math.sin(Math.PI * t) ** 1.4;
        let sample;
        if (state.analyserData && state.analyser) {
          const index = Math.min(state.analyserData.length - 1, Math.floor(t * state.analyserData.length));
          sample = (state.analyserData[index] - 128) / 128;
        } else {
          sample = Math.sin(t * 22 + state.drawPhase) * 0.12;
        }
        const synthetic = Math.sin(t * (18 + layer * 3) + state.drawPhase * (1 + layer * .08)) * (0.16 + intensity * .14);
        const y = centerY + (sample + synthetic) * amplitude * envelope + Math.sin(t * 8 + layer) * 4;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    ctx.shadowBlur = 0;
    const columns = 75;
    for (let i = 0; i < columns; i++) {
      const t = i / (columns - 1);
      const envelope = Math.sin(Math.PI * t) ** 1.9;
      const pulse = (Math.sin(t * 17 + state.drawPhase * 2.3) + 1) / 2;
      const h = envelope * (65 + intensity * 120) * (0.3 + pulse * 0.7);
      const x = t * width;
      ctx.strokeStyle = `rgba(156,108,255,${0.09 + envelope * 0.25})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, centerY - h);
      ctx.lineTo(x, centerY + h);
      ctx.stroke();
    }
  }

  els.tap.addEventListener('pointerdown', async (event) => {
    event.preventDefault();
    await startManual();
  });
  els.tap.addEventListener('pointerup', (event) => {
    event.preventDefault();
    stopManual();
  });
  els.tap.addEventListener('pointercancel', stopManual);
  els.tap.addEventListener('contextmenu', (event) => event.preventDefault());

  els.auto.addEventListener('click', async () => {
    if (state.autoEnabled) disableAuto();
    else await enableAuto();
  });

  async function boot() {
    els.desktopIp.textContent = window.location.host;
    await health();
    drawWave();
    if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname)) {
      showError('Para usar o microfone pelo Wi-Fi, abra o murn. mobile em HTTPS. O tutorial está em docs/ui.md.');
    }
  }

  boot();
})();
