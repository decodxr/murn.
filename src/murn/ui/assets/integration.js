(() => {
  const button = document.querySelector('#open-orbital');
  const toast = document.querySelector('#toast');
  if (!button) return;

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => toast.classList.remove('show'), 2200);
  }

  async function refresh() {
    try {
      const response = await fetch('/v1/integration/status', { cache: 'no-store' });
      if (!response.ok) return;
      const payload = await response.json();
      const connected = Boolean(payload?.orbital?.connected);
      button.classList.toggle('connected', connected);
      button.title = connected ? 'Orbital is connected · click to focus/open' : 'open Orbital';
    } catch (_) {}
  }

  async function openOrbital() {
    if (button.classList.contains('launching')) return;
    button.classList.add('launching');
    showToast('opening Orbital…');
    try {
      const response = await fetch('/v1/integration/open-orbital', { method: 'POST' });
      const payload = await response.json();
      if (!response.ok || payload?.ok === false) {
        throw new Error(payload?.error || `Orbital ${response.status}`);
      }
      button.classList.toggle('connected', Boolean(payload.connected || payload.already_running));
      showToast(payload.already_running ? 'Orbital already running' : 'Orbital opened');
    } catch (error) {
      showToast(`Orbital: ${error.message}`);
    } finally {
      button.classList.remove('launching');
    }
  }

  button.addEventListener('click', openOrbital);

  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'o') {
      event.preventDefault();
      openOrbital();
    }
  });

  refresh();
  setInterval(refresh, 20000);
})();
