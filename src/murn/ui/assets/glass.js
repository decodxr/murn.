(() => {
  let activeSurface = null;
  let frame = 0;
  let pointerX = 0;
  let pointerY = 0;

  const selector = '.desktop-topbar, .panel, .composer';

  function clearSurface(surface) {
    if (!surface) return;
    surface.style.setProperty('--glass-pointer-opacity', '0');
  }

  function paint() {
    frame = 0;
    const target = document.elementFromPoint(pointerX, pointerY)?.closest?.(selector) || null;

    if (target !== activeSurface) {
      clearSurface(activeSurface);
      activeSurface = target;
    }

    if (!activeSurface) return;
    const rect = activeSurface.getBoundingClientRect();
    activeSurface.style.setProperty('--glass-pointer-x', `${pointerX - rect.left}px`);
    activeSurface.style.setProperty('--glass-pointer-y', `${pointerY - rect.top}px`);
    activeSurface.style.setProperty('--glass-pointer-opacity', '1');
  }

  document.addEventListener('pointermove', (event) => {
    pointerX = event.clientX;
    pointerY = event.clientY;
    if (!frame) frame = requestAnimationFrame(paint);
  }, { passive: true });

  document.addEventListener('pointerleave', () => {
    clearSurface(activeSurface);
    activeSurface = null;
  });

  window.addEventListener('blur', () => {
    clearSurface(activeSurface);
    activeSurface = null;
  });
})();
