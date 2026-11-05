(() => {
  const notice = document.querySelector('#camera-access');
  const label = document.querySelector('#camera-access-status');
  const enable = document.querySelector('#camera-access-enable');
  if (!notice || !label || !enable) return;

  let state = 'checking';
  let permissionHandle = null;
  let requesting = false;
  let leaving = false;

  function display(next) {
    if (leaving) return;
    state = next;
    notice.dataset.state = next;
    notice.hidden = next === 'granted';
    enable.hidden = next === 'granted' || next === 'unavailable' || next === 'requesting';
    enable.disabled = requesting;
    if (next === 'denied') {
      label.textContent = 'Camera blocked. Allow access in this site’s browser settings.';
      enable.textContent = 'Check again';
    } else if (next === 'unavailable') {
      label.textContent = 'Camera unavailable. You can still enter a gift code manually.';
    } else if (next === 'requesting') {
      label.textContent = 'Requesting camera access…';
    } else if (next === 'prompt') {
      label.textContent = 'Camera permission is needed for QR scanning.';
      enable.textContent = 'Enable Camera';
    }
    window.dispatchEvent(new CustomEvent('umerrick:camera-status', {detail: {state: next}}));
  }

  async function check() {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) return 'unavailable';
    if (navigator.permissions?.query) {
      try {
        const handle = await navigator.permissions.query({name: 'camera'});
        if (permissionHandle && permissionHandle !== handle) permissionHandle.onchange = null;
        permissionHandle = handle;
        handle.onchange = () => { if (!requesting) display(handle.state); };
        return handle.state;
      } catch (_) { /* Some browsers do not expose camera permission queries. */ }
    }
    if (navigator.mediaDevices.enumerateDevices) {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        if (devices.some(device => device.kind === 'videoinput' && device.label)) return 'granted';
      } catch (_) { /* A button remains available when device labels cannot be read. */ }
    }
    return 'prompt';
  }

  async function refresh() {
    if (requesting || leaving) return;
    const next = await check();
    if (!requesting && !leaving) display(next);
  }

  async function requestCamera() {
    if (requesting) return;
    requesting = true;
    display('requesting');
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: false, video: {facingMode: {ideal: 'environment'}}});
      display('granted');
    } catch (error) {
      display(error?.name === 'NotAllowedError' || error?.name === 'PermissionDeniedError' ? 'denied' : 'unavailable');
    } finally {
      if (stream) stream.getTracks().forEach(track => track.stop());
      requesting = false;
      enable.disabled = false;
    }
  }

  enable.addEventListener('click', () => {
    if (state === 'denied') void refresh();
    else void requestCamera();
  });
  window.umerrickCameraPermission = {
    get state() { return state; },
    refresh,
    markGranted: () => display('granted'),
    markDenied: () => display('denied'),
    markUnavailable: () => display('unavailable'),
  };
  window.addEventListener('pageshow', () => { leaving = false; void refresh(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void refresh(); });
  window.addEventListener('pagehide', () => {
    leaving = true;
    if (permissionHandle) permissionHandle.onchange = null;
  });
  void refresh();
})();
