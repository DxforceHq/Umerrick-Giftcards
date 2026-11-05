(() => {
  const camera = document.querySelector('#camera');
  const start = document.querySelector('#camera-start');
  const message = document.querySelector('#camera-message');
  const form = document.querySelector('#manual-form');
  const codeInput = document.querySelector('#manual-code');
  const empty = document.querySelector('#empty-card');
  const result = document.querySelector('#card-result');
  const error = document.querySelector('#scanner-error');
  if (!camera || !start || !message || !form || !codeInput || !result || !error) return;

  let starting = false;
  let scanning = false;
  let processing = false;
  let waitingTimer = null;
  let cameraVideo = null;
  let mediaStream = null;
  let frameRequest = null;
  let startupTimer = null;
  let startAttempt = 0;
  let lastFrameAt = 0;
  let framesSeen = 0;
  let audioContext = null;
  const frameCanvas = document.createElement('canvas');
  const frameContext = frameCanvas.getContext('2d', {willReadFrequently: true});

  const csrftoken = () => document.querySelector('input[name=csrfmiddlewaretoken]')?.value || '';
  const fmt = value => value ? new Date(value).toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'}) : '—';
  const setMessage = text => { message.textContent = text; };
  const showError = text => { error.className = 'notice error'; error.textContent = text; error.hidden = false; };
  const hideError = () => { error.textContent = ''; error.hidden = true; };

  function prepareAudio() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    try {
      if (!audioContext || audioContext.state === 'closed') audioContext = new AudioContextClass();
      if (audioContext.state === 'suspended') void audioContext.resume().catch(() => {});
    } catch (_) { audioContext = null; }
  }

  function closeAudio() {
    const context = audioContext;
    audioContext = null;
    if (context && context.state !== 'closed') void context.close().catch(() => {});
  }

  function beepOnce() {
    const context = audioContext;
    if (!context || context.state !== 'running') return false;
    try {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      const at = context.currentTime + 0.005;
      oscillator.type = 'square';
      oscillator.frequency.setValueAtTime(1100, at);
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.linearRampToValueAtTime(0.045, at + 0.008);
      gain.gain.setValueAtTime(0.045, at + 0.085);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.115);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.onended = () => {
        oscillator.disconnect();
        gain.disconnect();
        if (audioContext === context) closeAudio();
      };
      oscillator.start(at);
      oscillator.stop(at + 0.12);
      return true;
    } catch (_) { return false; }
  }

  async function lookup(value, isQr = false) {
    hideError();
    try {
      const response = await fetch('/api/card/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrftoken()},
        body: JSON.stringify(isQr ? {qr: value} : {code: value}),
      });
      const card = await response.json();
      if (!response.ok) throw Error(card.error || 'Card lookup failed.');
      showCard(card);
      return true;
    } catch (err) {
      showError(err.message || 'Card lookup failed.');
      return false;
    }
  }

  function showCard(card) {
    if (waitingTimer) clearInterval(waitingTimer);
    empty.hidden = true;
    result.hidden = false;
    document.querySelector('#card-kind').textContent = card.kind;
    document.querySelector('#card-code').textContent = card.code;
    const badge = document.querySelector('#card-status');
    badge.textContent = card.status;
    badge.className = `badge ${card.status.toLowerCase()}`;
    const dates = document.querySelector('#card-dates');
    dates.replaceChildren();
    const facts = [['Activated', fmt(card.activated_at)], ['Eligible from', fmt(card.eligible_at)], ['Expires', fmt(card.expires_at)]];
    if (card.activation_purchase_amount !== null) {
      facts.push(['Spent at activation', `₦${Number(card.activation_purchase_amount).toLocaleString('en-NG', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`]);
    }
    facts.forEach(([label, value]) => {
      const dt = document.createElement('dt');
      const dd = document.createElement('dd');
      dt.textContent = label;
      dd.textContent = value;
      dates.append(dt, dd);
    });
    const actions = document.querySelector('#card-actions');
    actions.replaceChildren();
    if (card.status === 'GENERATED') {
      const phoneLabel = document.createElement('label');
      phoneLabel.htmlFor = 'activation-phone';
      phoneLabel.textContent = 'Customer phone number';
      const phone = document.createElement('input');
      phone.id = 'activation-phone';
      phone.type = 'tel';
      phone.inputMode = 'numeric';
      phone.autocomplete = 'off';
      phone.pattern = '[0-9]{10}';
      phone.required = true;
      phone.maxLength = 10;
      phone.placeholder = '7037761997';
      phone.setAttribute('aria-describedby', 'activation-phone-prefix');
      const phoneEntry = document.createElement('div');
      phoneEntry.className = 'phone-input';
      const prefix = document.createElement('span');
      prefix.id = 'activation-phone-prefix';
      prefix.textContent = '+234';
      phoneEntry.append(prefix, phone);
      const amountLabel = document.createElement('label');
      amountLabel.htmlFor = 'activation-spend';
      amountLabel.textContent = 'Amount spent at activation (₦)';
      const amount = document.createElement('input');
      amount.id = 'activation-spend';
      amount.type = 'number';
      amount.min = '0';
      amount.step = '0.01';
      amount.inputMode = 'decimal';
      amount.placeholder = 'e.g. 50000';
      const button = document.createElement('button');
      button.className = 'primary';
      button.textContent = 'Confirm activation';
      button.addEventListener('click', () => activate(card.id, phone.value, amount.value));
      actions.append(phoneLabel, phoneEntry, amountLabel, amount, button);
    } else if (card.status === 'READY') {
      const label = document.createElement('label');
      label.textContent = 'Eligible purchase amount (₦)';
      label.htmlFor = 'purchase-amount';
      const amount = document.createElement('input');
      amount.id = 'purchase-amount';
      amount.type = 'number';
      amount.min = '.01';
      amount.step = '.01';
      amount.placeholder = 'e.g. 50000';
      const preview = document.createElement('button');
      preview.className = 'secondary';
      preview.textContent = 'Preview discount';
      preview.addEventListener('click', () => previewDiscount(card.id, amount.value));
      actions.append(label, amount, preview);
    } else if (card.status === 'WAITING') {
      const eligible = Date.parse(card.eligible_at);
      const offset = Date.parse(card.server_now) - Date.now();
      const wait = document.createElement('p');
      wait.className = 'note';
      const tick = () => {
        const remaining = Math.max(0, eligible - (Date.now() + offset));
        wait.textContent = remaining
          ? `Redemption available in ${Math.floor(remaining / 3600000)}h ${Math.floor((remaining % 3600000) / 60000)}m. The server checks the exact eligibility time.`
          : 'Redemption is available. Scan the card again to continue.';
      };
      tick();
      waitingTimer = setInterval(tick, 60000);
      actions.append(wait);
    } else if (card.status === 'EXPIRED') {
      const note = document.createElement('p');
      note.className = 'notice error';
      note.textContent = card.rejection_reason || 'This card has expired and cannot be redeemed.';
      actions.append(note);
    }
  }

  async function post(url, body) {
    const response = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrftoken()},
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Request failed.');
    return data;
  }

  async function activate(id, customerPhone, activationPurchaseAmount) {
    hideError();
    if (!/^[0-9]{10}$/.test(customerPhone)) {
      showError('Enter the customer phone number: exactly 10 digits after +234.');
      document.querySelector('#activation-phone')?.focus();
      return;
    }
    if (!await window.umerrickConfirm({
      title: 'Activate this gift card?',
      description: 'The 72-hour waiting period and 60-day validity begin immediately after activation.',
      confirmLabel: 'Activate card',
    })) return;
    try { showCard(await post(`/api/card/${id}/activate/`, {customer_phone: customerPhone, activation_purchase_amount: activationPurchaseAmount})); }
    catch (err) { showError(err.message); }
  }

  async function previewDiscount(id, amount) {
    hideError();
    try {
      const preview = await post(`/api/card/${id}/preview/`, {amount});
      if (!await window.umerrickConfirm({
        title: 'Confirm redemption?',
        description: 'Review the purchase and discount. This card can only be redeemed once.',
        details: [
          ['Purchase', `₦${Number(preview.purchase_amount).toLocaleString()}`],
          ['Discount', `₦${Number(preview.discount_amount).toLocaleString()}`],
          ['Customer pays', `₦${Number(preview.payable_amount).toLocaleString()}`],
        ],
        confirmLabel: 'Redeem card',
      })) return;
      const done = await post(`/api/card/${id}/redeem/`, {amount});
      showError(`Redemption complete. Customer pays ₦${Number(done.payable_amount).toLocaleString()}.`);
      error.className = 'notice success';
    } catch (err) { showError(err.message); }
  }

  async function stopCamera({keepAudio = false} = {}) {
    startAttempt += 1;
    starting = false;
    scanning = false;
    if (frameRequest !== null) cancelAnimationFrame(frameRequest);
    frameRequest = null;
    if (startupTimer !== null) clearTimeout(startupTimer);
    startupTimer = null;
    if (cameraVideo) {
      cameraVideo.pause();
      cameraVideo.srcObject = null;
      cameraVideo = null;
    }
    if (mediaStream) mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
    camera.replaceChildren();
    if (!keepAudio) closeAudio();
    start.disabled = false;
    start.textContent = 'Scan another card';
  }

  function scanFrame(now) {
    if (!scanning || processing) return;
    frameRequest = requestAnimationFrame(scanFrame);
    if (now - lastFrameAt < 100 || !cameraVideo || cameraVideo.readyState < 2 || !cameraVideo.videoWidth) return;
    lastFrameAt = now;
    framesSeen += 1;
    const viewWidth = camera.clientWidth;
    const viewHeight = camera.clientHeight;
    if (!viewWidth || !viewHeight) return;
    const sourceWidth = cameraVideo.videoWidth;
    const sourceHeight = cameraVideo.videoHeight;
    const viewAspect = viewWidth / viewHeight;
    let sx = 0, sy = 0, sw = sourceWidth, sh = sourceHeight;
    if (sourceWidth / sourceHeight > viewAspect) {
      sw = sourceHeight * viewAspect;
      sx = (sourceWidth - sw) / 2;
    } else {
      sh = sourceWidth / viewAspect;
      sy = (sourceHeight - sh) / 2;
    }
    const scale = Math.min(1, 1280 / Math.max(sw, sh));
    const width = Math.max(1, Math.round(sw * scale));
    const height = Math.max(1, Math.round(sh * scale));
    if (frameCanvas.width !== width || frameCanvas.height !== height) {
      frameCanvas.width = width;
      frameCanvas.height = height;
    }
    try {
      frameContext.drawImage(cameraVideo, sx, sy, sw, sh, 0, 0, width, height);
      const pixels = frameContext.getImageData(0, 0, width, height);
      const decoded = jsQR(pixels.data, width, height, {inversionAttempts: 'attemptBoth'});
      if (decoded?.data) void onDecoded(decoded.data);
    } catch (err) {
      void stopCamera();
      setMessage('Camera frames could not be read. Try again or enter the printed code.');
      console.error('QR frame decoding failed:', err);
    }
  }

  async function onDecoded(raw) {
    if (processing) return;
    processing = true;
    const beepStarted = beepOnce();
    setMessage('QR code detected. Checking card…');
    await stopCamera({keepAudio: beepStarted});
    const attempt = startAttempt;
    start.disabled = true;
    start.textContent = 'Checking card…';
    try {
      await new Promise(resolve => setTimeout(resolve, 2000));
      if (attempt !== startAttempt) return;
      setMessage('Verifying card with the server…');
      const valid = await lookup(raw, true);
      if (attempt === startAttempt) setMessage(valid ? 'Card verified. Review its status and choose the next action.' : 'QR code could not be verified. Scan again or enter the printed code.');
    } finally {
      processing = false;
      if (attempt === startAttempt) {
        start.disabled = false;
        start.textContent = 'Scan another card';
      }
    }
  }

  async function startCamera() {
    if (starting || processing) return;
    if (scanning) {
      await stopCamera();
      setMessage('Camera stopped. You can scan another card or enter its code.');
      return;
    }
    if (!window.isSecureContext) {
      setMessage('Camera access requires HTTPS or localhost. Open the secure U_MERRICK address and try again.');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setMessage('Camera access is unavailable in this browser. Enter the printed code manually.');
      return;
    }
    if (typeof jsQR !== 'function' || !frameContext) {
      setMessage('The QR decoder did not load. Refresh this page or enter the printed code manually.');
      return;
    }
    prepareAudio();
    starting = true;
    const attempt = ++startAttempt;
    start.disabled = true;
    setMessage('Requesting camera permission…');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {facingMode: {ideal: 'environment'}, width: {ideal: 1280}, height: {ideal: 720}},
      });
      if (attempt !== startAttempt) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      mediaStream = stream;
      stream.getVideoTracks().forEach(track => track.addEventListener('ended', () => {
        if (attempt !== startAttempt) return;
        void stopCamera();
        setMessage('Camera disconnected. Try again or enter the printed code.');
      }));
      window.umerrickCameraPermission?.markGranted();
      cameraVideo = document.createElement('video');
      cameraVideo.autoplay = true;
      cameraVideo.muted = true;
      cameraVideo.playsInline = true;
      cameraVideo.setAttribute('playsinline', '');
      cameraVideo.srcObject = stream;
      camera.replaceChildren(cameraVideo);
      scanning = true;
      framesSeen = 0;
      lastFrameAt = 0;
      start.textContent = 'Stop camera';
      setMessage('Camera opened. Center the QR code in the preview to scan.');
      const playResult = cameraVideo.play();
      if (playResult?.catch) playResult.catch(err => {
        if (attempt !== startAttempt) return;
        void stopCamera();
        setMessage(`Camera video could not play: ${err.message || 'try again or use the printed code.'}`);
      });
      frameRequest = requestAnimationFrame(scanFrame);
      startupTimer = setTimeout(() => {
        if (!scanning || attempt !== startAttempt) return;
        setMessage(framesSeen ? 'Still looking for a QR code. Keep it centered, move closer and hold steady.' : 'Camera opened, but no video frames arrived. Try another camera or enter the printed code.');
      }, 8000);
    } catch (err) {
      const name = err?.name || '';
      const detail = String(err?.message || err);
      if (name === 'NotAllowedError' || /permission|denied/i.test(detail)) {
        window.umerrickCameraPermission?.markDenied();
        setMessage('Camera permission was denied. Allow camera access in browser settings and try again.');
      } else if (name === 'NotFoundError' || /not found|no camera/i.test(detail)) {
        window.umerrickCameraPermission?.markUnavailable();
        setMessage('No camera was found. Enter the printed code manually.');
      } else if (name === 'NotReadableError' || /in use|could not start video/i.test(detail)) {
        setMessage('The camera is in use by another app. Close that app and try again.');
      } else {
        setMessage('Camera scanning could not start. Try again or enter the printed code.');
      }
      closeAudio();
    } finally {
      if (attempt === startAttempt) {
        starting = false;
        start.disabled = false;
      }
    }
  }

  start.addEventListener('click', startCamera);
  function onPermissionStatus(state) {
    if (starting || scanning || processing) return;
    if (state === 'granted') setMessage('Camera ready. Start scanning or use the printed code.');
    else if (state === 'denied') setMessage('Camera blocked. Allow access in browser settings or enter the printed code.');
    else if (state === 'unavailable') setMessage('Camera unavailable. Enter the printed code manually.');
    else if (state === 'prompt') setMessage('Enable Camera above or select Start camera to request access.');
  }
  window.addEventListener('umerrick:camera-status', event => onPermissionStatus(event.detail?.state));
  onPermissionStatus(window.umerrickCameraPermission?.state);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (processing) return;
    processing = true;
    await stopCamera();
    setMessage('Looking up the printed gift code…');
    const valid = await lookup(codeInput.value.trim());
    setMessage(valid ? 'Card found. Review its status and choose the next action.' : 'Code not found. Check the printed code and try again.');
    processing = false;
  });
  window.addEventListener('pagehide', () => { void stopCamera(); });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && scanning) void stopCamera();
  });
})();
