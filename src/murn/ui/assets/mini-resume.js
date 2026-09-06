(() => {
  const params = new URLSearchParams(location.search);
  const requested = params.get('resume_session') || localStorage.getItem('murn:mini-resume-session');
  if (!requested) return;

  let attempts = 0;
  const timer = setInterval(() => {
    attempts += 1;
    const items = [...document.querySelectorAll('.session-item')];
    const target = items.find((item) => item.dataset.sessionId === requested);
    if (target) {
      clearInterval(timer);
      localStorage.removeItem('murn:mini-resume-session');
      target.querySelector('.session-open')?.click();
      return;
    }
    if (attempts >= 40) clearInterval(timer);
  }, 100);
})();
