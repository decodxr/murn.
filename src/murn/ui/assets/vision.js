(() => {
  const composer = document.querySelector('#composer');
  const input = document.querySelector('#message-input');
  const send = document.querySelector('#send-button');
  const attach = document.querySelector('.attach-button');
  const messageList = document.querySelector('#message-list');
  const toastEl = document.querySelector('#toast');

  if (!composer || !input || !send || !attach || !messageList) return;

  const state = {
    file: null,
    previewUrl: null,
    busy: false,
    visionModel: 'vision',
  };

  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = 'image/png,image/jpeg,image/webp';
  fileInput.hidden = true;
  fileInput.setAttribute('aria-hidden', 'true');
  document.body.appendChild(fileInput);

  const preview = document.createElement('div');
  preview.className = 'vision-attachment-preview';
  preview.innerHTML = `
    <img alt="imagem anexada" />
    <span class="vision-preview-copy">
      <span class="vision-preview-label">IMAGE / READY</span>
      <span class="vision-preview-meta"></span>
    </span>
    <button type="button" class="vision-preview-remove" aria-label="remover imagem">×</button>
  `;
  composer.appendChild(preview);

  attach.title = 'anexar imagem';
  attach.setAttribute('aria-label', 'anexar imagem');

  function toast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.classList.add('show');
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => toastEl.classList.remove('show'), 2600);
  }

  function humanSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function validImage(file) {
    return ['image/png', 'image/jpeg', 'image/webp'].includes(file?.type || '');
  }

  function setPendingFile(file) {
    if (!file) return;
    if (!validImage(file)) {
      toast('use PNG, JPEG ou WebP');
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      toast('imagem maior que 20 MB');
      return;
    }

    state.file = file;
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = URL.createObjectURL(file);

    const image = preview.querySelector('img');
    const meta = preview.querySelector('.vision-preview-meta');
    image.src = state.previewUrl;
    meta.textContent = `${file.name || 'clipboard image'} · ${humanSize(file.size)}`;
    preview.classList.add('show');
    attach.classList.add('vision-active');
    input.placeholder = 'pergunte algo sobre a imagem...';
    input.focus();
  }

  function clearPending({ keepPreviewUrl = false } = {}) {
    state.file = null;
    fileInput.value = '';
    preview.classList.remove('show');
    attach.classList.remove('vision-active');
    input.placeholder = 'ask murn...';
    if (!keepPreviewUrl && state.previewUrl) {
      URL.revokeObjectURL(state.previewUrl);
      state.previewUrl = null;
    }
  }

  function currentSessionId() {
    return document.querySelector('.session-item.active')?.dataset?.sessionId || '';
  }

  function escapeSelector(value) {
    if (window.CSS?.escape) return CSS.escape(value);
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }

  function appendMessageShell(role) {
    document.querySelector('#welcome-card')?.remove();

    const wrapper = document.createElement('article');
    wrapper.className = `message ${role === 'assistant' ? 'murn' : 'user'}`;

    const avatar = document.createElement('div');
    avatar.className = `avatar ${role === 'assistant' ? 'murn' : 'user'}`;
    if (role === 'assistant') {
      avatar.innerHTML = 'm<span>.</span>';
    } else {
      avatar.textContent = '>_';
    }

    const body = document.createElement('div');
    body.className = 'message-body';

    const head = document.createElement('div');
    head.className = 'message-head';

    const roleEl = document.createElement('span');
    roleEl.className = 'message-role';
    roleEl.textContent = role === 'assistant' ? 'murn.' : 'YOU';

    const time = document.createElement('span');
    time.className = 'message-time';
    time.textContent = new Intl.DateTimeFormat('pt-BR', {
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date());

    const content = document.createElement('div');
    content.className = 'message-content';

    head.append(roleEl, time);
    body.append(head, content);
    wrapper.append(avatar, body);
    messageList.appendChild(wrapper);
    messageList.scrollTop = messageList.scrollHeight;
    return { wrapper, body, content };
  }

  function appendVisionUser(imageUrl, question) {
    const message = appendMessageShell('user');
    const image = document.createElement('img');
    image.className = 'vision-message-image';
    image.src = imageUrl;
    image.alt = 'imagem enviada para análise';
    const caption = document.createElement('span');
    caption.className = 'vision-message-caption';
    caption.textContent = question;
    message.content.append(image, caption);
    return message;
  }

  function appendVisionAssistant() {
    const message = appendMessageShell('assistant');
    const card = document.createElement('div');
    card.className = 'vision-processing';
    card.innerHTML = `
      <span class="tool-icon">◉</span>
      <span>
        <span class="tool-name">analisando imagem</span>
        <span class="vision-model">${state.visionModel} · local vision</span>
      </span>
      <span class="spinner"></span>
    `;
    message.body.appendChild(card);
    return { ...message, card };
  }

  function renderStoredVisionImages(root = document) {
    const nodes = root.querySelectorAll?.('.message-content:not([data-vision-rendered])') || [];
    const pattern = /^\[\[murn-image:(\/v1\/vision\/files\/[A-Za-z0-9._-]+)\]\]\s*/;

    nodes.forEach((content) => {
      const raw = content.textContent || '';
      const match = raw.match(pattern);
      if (!match) return;

      const imageUrl = match[1];
      const rest = raw.replace(pattern, '');
      content.textContent = '';

      const image = document.createElement('img');
      image.className = 'vision-message-image';
      image.src = imageUrl;
      image.alt = 'imagem enviada para análise';
      content.appendChild(image);

      if (rest) {
        const caption = document.createElement('span');
        caption.className = 'vision-message-caption';
        caption.textContent = rest;
        content.appendChild(caption);
      }
      content.dataset.visionRendered = '1';
    });
  }

  async function refreshVisionHealth() {
    try {
      const response = await fetch('/health');
      if (!response.ok) return;
      const health = await response.json();
      state.visionModel = health.vision_model || 'vision';
      const settingsVision = document.querySelector('#settings-vision');
      if (settingsVision) {
        settingsVision.textContent = health.vision ? `${state.visionModel} · ready` : `${state.visionModel} · missing`;
      }
    } catch (_) {}
  }

  async function sendVision() {
    if (!state.file || state.busy) return;

    const question = input.value.trim() || 'Analise esta imagem detalhadamente.';
    const file = state.file;
    const localPreviewUrl = state.previewUrl;
    const sessionId = currentSessionId();

    state.busy = true;
    send.disabled = true;
    attach.disabled = true;
    input.value = '';
    input.style.height = 'auto';

    appendVisionUser(localPreviewUrl, question);
    const assistant = appendVisionAssistant();
    clearPending({ keepPreviewUrl: true });

    try {
      const form = new FormData();
      form.append('file', file, file.name || 'image.png');
      form.append('message', question);
      if (sessionId) form.append('session_id', sessionId);

      const response = await fetch('/v1/vision/chat', {
        method: 'POST',
        body: form,
      });

      if (!response.ok) {
        let detail = `vision request failed: ${response.status}`;
        try {
          const body = await response.json();
          detail = body.detail || detail;
        } catch (_) {}
        throw new Error(detail);
      }

      const result = await response.json();
      assistant.card.remove();
      assistant.content.textContent = result.message || '';

      if (result.session_id) {
        try {
          const sessionResponse = await fetch(`/v1/sessions/${encodeURIComponent(result.session_id)}`);
          if (sessionResponse.ok) {
            const session = await sessionResponse.json();
            const title = document.querySelector('#conversation-title');
            if (title) title.textContent = session.title || 'New Chat';

            const active = document.querySelector(`.session-item[data-session-id="${escapeSelector(result.session_id)}"]`);
            if (active) {
              const titleEl = active.querySelector('.session-title');
              const previewEl = active.querySelector('.session-preview');
              if (titleEl) titleEl.textContent = session.title || 'New chat';
              if (previewEl) previewEl.textContent = `${session.messages?.length || 0} messages`;
            }
          }
        } catch (_) {}
      }

      messageList.scrollTop = messageList.scrollHeight;
    } catch (error) {
      assistant.card.remove();
      assistant.content.textContent = `error: ${error.message}`;
      toast(error.message);
    } finally {
      state.busy = false;
      send.disabled = false;
      attach.disabled = false;
      input.focus();
    }
  }

  attach.addEventListener('click', () => {
    if (!state.busy) fileInput.click();
  });

  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (file) setPendingFile(file);
  });

  preview.querySelector('.vision-preview-remove').addEventListener('click', () => clearPending());

  composer.addEventListener('dragover', (event) => {
    if ([...(event.dataTransfer?.items || [])].some((item) => item.type.startsWith('image/'))) {
      event.preventDefault();
      composer.classList.add('vision-drop');
    }
  });

  composer.addEventListener('dragleave', () => composer.classList.remove('vision-drop'));

  composer.addEventListener('drop', (event) => {
    composer.classList.remove('vision-drop');
    const file = [...(event.dataTransfer?.files || [])].find((item) => item.type.startsWith('image/'));
    if (!file) return;
    event.preventDefault();
    setPendingFile(file);
  });

  input.addEventListener('paste', (event) => {
    const item = [...(event.clipboardData?.items || [])].find((entry) => entry.type.startsWith('image/'));
    const file = item?.getAsFile();
    if (file) setPendingFile(file);
  }, true);

  // desktop.js owns normal chat. Capture only submissions that currently carry
  // an image and stop them before the normal text-only handler sees the event.
  composer.addEventListener('submit', (event) => {
    if (!state.file) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    sendVision();
  }, true);

  input.addEventListener('keydown', (event) => {
    if (!state.file || event.key !== 'Enter' || event.shiftKey) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    sendVision();
  }, true);

  const observer = new MutationObserver(() => renderStoredVisionImages(messageList));
  observer.observe(messageList, { childList: true, subtree: true, characterData: true });

  renderStoredVisionImages(messageList);
  refreshVisionHealth();
})();
