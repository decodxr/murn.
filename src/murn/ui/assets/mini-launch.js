(() => {
  const button = document.querySelector('#open-mini');
  if (!button) return;

  async function enterMini() {
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
})();
