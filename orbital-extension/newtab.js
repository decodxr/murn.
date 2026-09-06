const API = 'http://127.0.0.1:7332';

const $ = (selector) => document.querySelector(selector);
const els = {
  form: $('#search-form'),
  input: $('#search-input'),
  tabs: $('#tabs'),
  murnDot: $('#murn-dot'),
  murnStatus: $('#murn-status'),
  openMurn: $('#open-murn'),
  askMurn: $('#ask-murn'),
  clock: $('#clock'),
};

async function health() {
  try {
    const response = await fetch(`${API}/health`, { cache: 'no-store' });
    if (!response.ok) throw new Error('offline');
    els.murnDot.classList.add('online');
    els.murnStatus.textContent = 'murn. ready';
    return true;
  } catch (_) {
    els.murnDot.classList.remove('online');
    els.murnStatus.textContent = 'murn. offline';
    return false;
  }
}

async function showTabs() {
  const tabs = await chrome.tabs.query({ currentWindow: true });
  const visible = tabs.filter((tab) => !String(tab.url || '').startsWith('chrome://newtab'));
  els.tabs.innerHTML = '';
  if (!visible.length) {
    els.tabs.innerHTML = '<span class="muted">no other tabs open.</span>';
    return;
  }

  for (const tab of visible.slice(0, 9)) {
    const button = document.createElement('button');
    button.className = 'tab-item';
    button.innerHTML = `<strong></strong><span></span>`;
    button.querySelector('strong').textContent = tab.title || 'Untitled';
    button.querySelector('span').textContent = tab.url || '';
    button.addEventListener('click', async () => {
      await chrome.tabs.update(tab.id, { active: true });
    });
    els.tabs.appendChild(button);
  }
}

async function openMurnPanel(prompt = '') {
  const current = await chrome.windows.getCurrent();
  if (prompt) {
    await chrome.storage.session.set({
      pendingPrompt: {
        prompt,
        context: {},
        createdAt: Date.now(),
      },
    });
  }
  try {
    await chrome.sidePanel.open({ windowId: current.id });
  } catch (error) {
    console.warn(error);
  }
}

async function submit(text) {
  const value = String(text || '').trim();
  if (!value) return;

  const lower = value.toLowerCase();
  if (lower === 'murn.' || lower === 'murn') {
    await openMurnPanel('');
    return;
  }

  if (lower.startsWith('murn.')) {
    await openMurnPanel(value.slice(5).trim());
    return;
  }

  if (lower.startsWith('murn ')) {
    await openMurnPanel(value.slice(5).trim());
    return;
  }

  await chrome.runtime.sendMessage({ type: 'search', text: value, disposition: 'CURRENT_TAB' });
}

els.form.addEventListener('submit', (event) => {
  event.preventDefault();
  submit(els.input.value);
});

els.openMurn.addEventListener('click', async () => {
  const result = await chrome.runtime.sendMessage({ type: 'open-murn' });
  if (!result?.ok) await openMurnPanel('');
});

els.askMurn.addEventListener('click', () => openMurnPanel(''));

document.querySelectorAll('[data-url]').forEach((button) => {
  button.addEventListener('click', () => {
    location.href = button.dataset.url;
  });
});

function updateClock() {
  els.clock.textContent = new Intl.DateTimeFormat('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date());
}

chrome.tabs.onCreated.addListener(showTabs);
chrome.tabs.onRemoved.addListener(showTabs);
chrome.tabs.onUpdated.addListener((_id, info) => {
  if (info.title || info.url) showTabs();
});

(async () => {
  await Promise.all([health(), showTabs()]);
  updateClock();
  setInterval(updateClock, 30000);
  setInterval(health, 20000);
})();
