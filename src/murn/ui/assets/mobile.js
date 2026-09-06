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
    assistantTalk: $('#assistant-talk'),
    assistantDockTitle: $('#assistant-dock-title'),
    assistantDockSubtitle: $('#assistant-dock-subtitle'),
    quickActions: $$('.mobile-quick-action'),
    tap: $('#tap-to-talk'),
    auto: $('#auto-listen'),
    canvas: $('#wave-canvas'),
    error: $('#mobile-error'),
    connection: $('#phone-connection'),
    techline: $('#phone-techline'),
    desktopIp: $('#desktop-ip'),
  };

  const ctx = els.canvas.getContext('2d', { alpha: true });

  const state = {
    health: null,
    mode: localStorage.getItem('murn:mobile-mode') === 'voice' ? 'voice' : 'assistant',
    intent: localStorage.getItem('murn:mobile-intent') || 'ask',
    voiceState: 'standby',
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
  };

  const voiceLabels = {
    standby: ['STANDBY', 'ready when you are'],
    listening: ['LISTENING', 'capturing your voice'],
    transcribing: ['TRANSCRIBING', 'turning speech into text'],
    thinking: ['THINKING', 'murn. is processing locally'],
    speaking: ['SPEAKING', 'murn. is talking'],
  };

  const assistantLabels = {
    standby: ['READY', 'tap and hold to talk'],
    listening: ['LISTENING', 'keep holding while you speak'],
    transcribing: ['HEARD YOU', 'turning speech into text'],
    thinking: ['THINKING', 'working on it locally'],
    speaking: ['SPEAKING', 'murn. is answering'],
  };

  const intentLabels = {
    ask: ['Talk to murn...', 'hold to speak · ask mode'],
    create: ['Tell murn. what to create...', 'hold to speak · create mode'],
    code: ['Tell murn. what to build...', 'hold to speak · code mode'],
    plan: ['Tell murn. what to plan...', 'hold to speak · plan mode'],
  };

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
    if (persist) localStorage.setItem('murn:mobile-mode', mode);

    if (mode === 'assistant' && state.autoEnabled) disableAuto();
    setVoiceState(state.voiceState);
  }

  function selectIntent(intent) {
    if (!intentLabels[intent]) intent = 'ask';
    state.intent = intent;
    localStorage.setItem('murn:mobile-intent', intent);
    els.quickActions.forEach((button) => {
      button.classList.toggle('active', button.dataset.intent === intent);
    });
    const [title, subtitle] = intentLabels[intent];
    els.assistantDockTitle.textContent = title;
    els.assistantDockSubtitle.textContent = subtitle;
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
      const response = await fetch('/health', { cache: 'no-store' });
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
        throw new Error('O microfone exige HTTPS no celular. Abra a URL HTTPS do murn. mobile.');
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
    els.assistantTalk.classList.toggle('active', active);
  }

  async function startManual(button) {
    if (state.busy || state.manual || state.manualStarting) return;
    if (state.autoEnabled) disableAuto();

    state.manualStarting = true;
    state.holdSource = button;
    try {
      await ensureAudio();
      if (state.holdSource !== button) return;

      state.manual = true;
      markHoldControls(true);
      setVoiceState('listening');

      const recorder = buildRecorder(async (blob) => {
        state.manual = false;
        markHoldControls(false);
        if (blob.size > 900) await sendRemoteVoice(blob);
        else setVoiceState('standby');
      });
      recorder.start();
    } catch (error) {
      state.manual = false;
      state.holdSource = null;
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
    if (state.autoEnabled || state.busy) return;
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
      form.append('intent', state.intent);

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
      const heard = String(result.transcript || '').trim();
      setVoiceState(
        'thinking',
        heard ? `“${heard.slice(0, 58)}${heard.length > 58 ? '…' : ''}”` : null,
      );

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
      const response = await fetch(url, { cache: 'no-store' });
      if (!response.ok) throw new Error('failed to download voice response');
      const buffer = await response.arrayBuffer();
      const decoded = await state.audioContext.decodeAudioData(buffer.slice(0));

      const source = state.audioContext.createBufferSource();
      const analyser = state.audioContext.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = 0.78;

      source.buffer = decoded;
      source.connect(analyser);
      analyser.connect(state.audioContext.destination);

      state.playbackSource = source;
      state.outputAnalyser = analyser;
      state.outputData = new Uint8Array(analyser.fftSize);

      source.onended = () => {
        state.playbackSource = null;
        state.outputAnalyser = null;
        state.outputData = null;
        state.busy = false;
        setVoiceState(state.autoEnabled ? 'listening' : 'standby');
      };

      setVoiceState('speaking');
      source.start();
    } catch (error) {
      state.playbackSource = null;
      state.outputAnalyser = null;
      state.outputData = null;
      state.busy = false;
      setVoiceState(state.autoEnabled ? 'listening' : 'standby');
      showError(error.message);
    }
  }

  function getVisualSamples() {
    const [analyser, data] = visualSource();
    if (!analyser || !data) return { data: null, level: 0 };
    const level = analyserRms(analyser, data);
    return { data, level };
  }

  function drawWave(timestamp = 0) {
    requestAnimationFrame(drawWave);
    if (timestamp - state.lastDraw < 30) return;
    state.lastDraw = timestamp;

    const width = els.canvas.width;
    const height = els.canvas.height;
    ctx.clearRect(0, 0, width, height);

    state.drawPhase += 0.04;
    const visual = getVisualSamples();
    const busyFloor = ['transcribing', 'thinking'].includes(state.voiceState) ? 0.18 : 0;
    const speakingFloor = state.voiceState === 'speaking' ? 0.14 : 0;
    const listeningFloor = state.voiceState === 'listening' ? 0.08 : 0;
    const intensity = Math.min(1, visual.level * 11 + busyFloor + speakingFloor + listeningFloor + 0.045);
    const centerY = height * 0.5;

    const mainGradient = ctx.createLinearGradient(0, 0, width, 0);
    mainGradient.addColorStop(0, 'rgba(155,118,255,0)');
    mainGradient.addColorStop(.16, 'rgba(165,145,223,.32)');
    mainGradient.addColorStop(.48, 'rgba(229,226,239,.92)');
    mainGradient.addColorStop(.54, 'rgba(188,168,239,.88)');
    mainGradient.addColorStop(.84, 'rgba(165,145,223,.32)');
    mainGradient.addColorStop(1, 'rgba(155,118,255,0)');

    const sampleAt = (t) => {
      if (!visual.data) return Math.sin(t * 16 + state.drawPhase) * .075;
      const index = Math.min(visual.data.length - 1, Math.floor(t * visual.data.length));
      return (visual.data[index] - 128) / 128;
    };

    for (let layer = 0; layer < 6; layer += 1) {
      ctx.beginPath();
      ctx.lineWidth = layer === 0 ? 3.0 : 1.0;
      ctx.strokeStyle = layer === 0
        ? mainGradient
        : `rgba(174,160,207,${Math.max(.035, .16 - layer * .022)})`;
      ctx.shadowBlur = layer === 0 ? 15 : 4;
      ctx.shadowColor = 'rgba(155,118,255,.42)';

      const phase = state.drawPhase * (1 + layer * .055) + layer * .8;
      const amplitude = 38 + intensity * 150 + layer * 7;
      for (let x = 0; x <= width; x += 5) {
        const t = x / width;
        const envelope = Math.sin(Math.PI * t) ** 1.25;
        const sourceSample = sampleAt(t);
        const ribbon = Math.sin(t * (13 + layer * 1.7) + phase) * (.12 + intensity * .10);
        const secondary = Math.sin(t * 27 - phase * .75) * (.035 + intensity * .025);
        const y = centerY + (sourceSample * .72 + ribbon + secondary) * amplitude * envelope;
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

    const dots = 62;
    for (let i = 0; i < dots; i += 1) {
      const t = i / (dots - 1);
      const envelope = Math.sin(Math.PI * t) ** 1.4;
      const wave = Math.sin(t * 14 + state.drawPhase * .8) * (26 + intensity * 90) * envelope;
      const x = t * width;
      const y = centerY + wave;
      ctx.fillStyle = `rgba(202,191,232,${.05 + envelope * .18})`;
      ctx.beginPath();
      ctx.arc(x, y, 1.1 + intensity * .7, 0, Math.PI * 2);
      ctx.fill();
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

  bindHold(els.tap);
  bindHold(els.assistantTalk);

  els.auto.addEventListener('click', async () => {
    if (state.autoEnabled) disableAuto();
    else await enableAuto();
  });

  els.modeAssistant.addEventListener('click', () => setMode('assistant'));
  els.modeVoice.addEventListener('click', () => setMode('voice'));

  els.quickActions.forEach((button) => {
    button.addEventListener('click', () => selectIntent(button.dataset.intent));
  });

  async function boot() {
    els.desktopIp.textContent = window.location.host;
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
