(() => {
  const button = document.querySelector('#open-mini');
  if (!button) return;

  function rememberActiveSession() {
    const active = document.querySelector('.session-item.active');
    const sessionId = active?.dataset?.sessionId;
    if (sessionId) localStorage.setItem('murn:mini-session', sessionId);
  }

  function resumeMiniSessionIfNeeded() {
    const params = new URLSearchParams(location.search);
    if (params.get('from') !== 'mini') return;
    const sessionId = localStorage.getItem('murn:mini-session');
    if (!sessionId) return;

    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      const target = [...document.querySelectorAll('.session-item')]
        .find((item) => item.dataset.sessionId === sessionId);
      if (target) {
        clearInterval(timer);
        target.querySelector('.session-open')?.click();
        return;
      }
      if (attempts >= 40) clearInterval(timer);
    }, 100);
  }

  async function enterMini() {
    rememberActiveSession();
    const invoke = window.__TAURI__?.core?.invoke;
    if (invoke) {
      try {
        await invoke('set_window_mode', { mode: 'mini' });
      } catch (error) {
        console.warn('native mini resize failed; opening mini UI anyway', error);
      }
    }
    location.href = `/ui/mini/index.html?ui=0.14.0&t=${Date.now()}`;
  }

  button.addEventListener('click', enterMini);
  document.addEventListener('keydown', (event) => {
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'm') {
      event.preventDefault();
      enterMini();
    }
  });

  resumeMiniSessionIfNeeded();
})();
