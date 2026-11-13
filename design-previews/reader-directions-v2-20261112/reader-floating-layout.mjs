/** Small DOM controller shared by the reader and its isolated design preview. */
export function clampOffset(offset, base, viewport, margin = 8) {
  const limit = (n, start, size, available) => Math.max(margin - start, Math.min(n, Math.max(margin, available - size - margin) - start));
  return { x: limit(offset.x, base.left, base.width, viewport.width), y: limit(offset.y, base.top, base.height, viewport.height) };
}

export function createReaderFloatingLayout(root, storageKey) {
  let offsets = {}, active = null, disposed = false;
  const desktop = () => window.matchMedia('(min-width: 761px)').matches;
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || '{}');
    for (const [id, point] of Object.entries(saved)) {
      if (/^[a-z-]+$/.test(id) && Number.isFinite(point?.x) && Number.isFinite(point?.y)) offsets[id] = point;
    }
  } catch { /* Storage is optional; dragging still works. */ }
  const store = () => { try { sessionStorage.setItem(storageKey, JSON.stringify(offsets)); } catch {} };
  const viewport = () => ({ width: window.innerWidth, height: window.innerHeight });
  const elements = () => root.querySelectorAll('[data-reader-float]');
  function apply(element, proposed) {
    const id = element.dataset.readerFloat;
    const old = element._readerOffset || { x: 0, y: 0 };
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const next = clampOffset(proposed, { left: rect.left - old.x, top: rect.top - old.y, width: rect.width, height: rect.height }, viewport());
    element.style.translate = `${next.x}px ${next.y}px`;
    element.dataset.readerMoved = String(Boolean(next.x || next.y));
    element._readerOffset = next;
    offsets[id] = next;
  }
  function refresh() {
    if (disposed || active) return;
    elements().forEach(element => {
      if (!desktop()) { element.style.translate = ''; element._readerOffset = { x: 0, y: 0 }; delete element.dataset.readerMoved; }
      else if (offsets[element.dataset.readerFloat]) apply(element, offsets[element.dataset.readerFloat]);
    });
  }
  function end(event) {
    if (!active || (event?.pointerId !== undefined && event.pointerId !== active.pointer)) return;
    const current = active; active = null;
    current.element.removeAttribute('data-reader-dragging');
    if (current.grip.hasPointerCapture(current.pointer)) current.grip.releasePointerCapture(current.pointer);
    store();
  }
  function start(event) {
    const grip = event.target.closest?.('[data-reader-grip]');
    const element = grip?.closest('[data-reader-float]');
    if (!desktop() || event.button !== 0 || !element || !root.contains(element)) return;
    event.preventDefault(); event.stopPropagation();
    active = { element, grip, pointer: event.pointerId, x: event.clientX, y: event.clientY, offset: element._readerOffset || { x: 0, y: 0 } };
    element.dataset.readerDragging = 'true';
    grip.setPointerCapture(event.pointerId);
  }
  function move(event) {
    if (!active || event.pointerId !== active.pointer) return;
    apply(active.element, { x: active.offset.x + event.clientX - active.x, y: active.offset.y + event.clientY - active.y });
  }
  function keys(event) {
    const grip = event.target.closest?.('[data-reader-grip]');
    const element = grip?.closest('[data-reader-float]');
    if (!desktop() || !element || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    const offset = element._readerOffset || { x: 0, y: 0 }, step = event.shiftKey ? 40 : 10;
    if (event.key === 'Home') {
      delete offsets[element.dataset.readerFloat]; element.style.translate = ''; element._readerOffset = { x: 0, y: 0 }; delete element.dataset.readerMoved;
    } else apply(element, { x: offset.x + (event.key === 'ArrowRight' ? step : event.key === 'ArrowLeft' ? -step : 0), y: offset.y + (event.key === 'ArrowDown' ? step : event.key === 'ArrowUp' ? -step : 0) });
    store();
  }
  root.addEventListener('pointerdown', start);
  root.addEventListener('keydown', keys);
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', end);
  window.addEventListener('pointercancel', end);
  window.addEventListener('blur', end);
  window.addEventListener('resize', refresh);
  const observer = new ResizeObserver(refresh); observer.observe(root);
  refresh();
  return {
    refresh,
    reset() { end(); offsets = {}; elements().forEach(element => { element.style.translate = ''; element._readerOffset = { x: 0, y: 0 }; delete element.dataset.readerMoved; }); store(); },
    destroy() { end(); disposed = true; observer.disconnect(); root.removeEventListener('pointerdown', start); root.removeEventListener('keydown', keys); window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); window.removeEventListener('pointercancel', end); window.removeEventListener('blur', end); window.removeEventListener('resize', refresh); },
  };
}
