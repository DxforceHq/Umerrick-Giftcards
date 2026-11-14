(() => {
  'use strict';
  const button = document.querySelector('#public-scan-button');
  const preview = document.querySelector('#public-scan-preview');
  const placeholder = document.querySelector('#public-scan-placeholder');
  const message = document.querySelector('#public-scan-message');
  const form = document.querySelector('#public-qr-form');
  const qrField = document.querySelector('#public-qr-value');
  if (!button || !preview || !message || !form || !qrField) return;

  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d', {willReadFrequently: true});
  let stream = null;
  let video = null;
  let frame = 0;
  let lastFrame = 0;
  let starting = false;
  let scanning = false;
  let submitting = false;
  let cameraAttempt = 0;

  function setMessage(value) { message.textContent = value; }

  function stopCamera() {
    cameraAttempt += 1;
    scanning = false;
    cancelAnimationFrame(frame);
    frame = 0;
    if (video) {
      video.pause();
      video.srcObject = null;
      video = null;
    }
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    preview.replaceChildren(placeholder);
    if (!submitting) {
      button.disabled = false;
      button.textContent = 'Scan QR code';
    }
  }

  function scanFrame(now) {
    if (!scanning || submitting) return;
    frame = requestAnimationFrame(scanFrame);
    if (now - lastFrame < 120 || !video || video.readyState < 2 || !video.videoWidth) return;
    lastFrame = now;
    const sourceWidth = video.videoWidth;
    const sourceHeight = video.videoHeight;
    const previewAspect = preview.clientWidth / preview.clientHeight;
    if (!Number.isFinite(previewAspect) || previewAspect <= 0) return;
    let sx = 0, sy = 0, sw = sourceWidth, sh = sourceHeight;
    if (sourceWidth / sourceHeight > previewAspect) {
      sw = sourceHeight * previewAspect;
      sx = (sourceWidth - sw) / 2;
    } else {
      sh = sourceWidth / previewAspect;
      sy = (sourceHeight - sh) / 2;
    }
    const scale = Math.min(1, 960 / Math.max(sw, sh));
    const width = Math.max(1, Math.round(sw * scale));
    const height = Math.max(1, Math.round(sh * scale));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    try {
      context.drawImage(video, sx, sy, sw, sh, 0, 0, width, height);
      const pixels = context.getImageData(0, 0, width, height);
      const result = window.jsQR(pixels.data, width, height, {inversionAttempts: 'attemptBoth'});
      if (!result?.data) return;
      submitting = true;
      stopCamera();
      setMessage('QR code detected. Checking your card…');
      qrField.value = result.data;
      form.requestSubmit();
    } catch (error) {
      stopCamera();
      setMessage('Camera frames could not be read. Try again or enter the printed code.');
      console.error('Public QR scan failed:', error);
    }
  }

  async function startCamera() {
    if (starting || submitting) return;
    if (scanning) {
      stopCamera();
      setMessage('Camera stopped. You can scan again or enter the printed code.');
      return;
    }
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setMessage('Camera access requires HTTPS or localhost. Enter the printed code instead.');
      return;
    }
    if (typeof window.jsQR !== 'function' || !context) {
      setMessage('The QR scanner did not load. Refresh the page or enter the printed code.');
      return;
    }
    starting = true;
    const attempt = ++cameraAttempt;
    button.disabled = true;
    setMessage('Requesting camera permission…');
    try {
      const acquired = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {facingMode: {ideal: 'environment'}, width: {ideal: 1280}, height: {ideal: 720}},
      });
      if (attempt !== cameraAttempt || document.hidden) {
        acquired.getTracks().forEach(track => track.stop());
        setMessage('Camera stopped. Start a new scan when you return.');
        return;
      }
      stream = acquired;
      video = document.createElement('video');
      video.autoplay = true;
      video.muted = true;
      video.playsInline = true;
      video.setAttribute('playsinline', '');
      video.srcObject = stream;
      preview.replaceChildren(video);
      await video.play();
      scanning = true;
      button.textContent = 'Stop camera';
      setMessage('Camera open. Hold the QR code steady in the frame.');
      stream.getVideoTracks().forEach(track => track.addEventListener('ended', () => {
        if (!scanning) return;
        stopCamera();
        setMessage('Camera disconnected. Try again or enter the printed code.');
      }));
      frame = requestAnimationFrame(scanFrame);
    } catch (error) {
      stopCamera();
      if (error?.name === 'NotAllowedError') setMessage('Camera permission was denied. Allow access in browser settings or enter the printed code.');
      else if (error?.name === 'NotFoundError') setMessage('No camera was found. Enter the printed code instead.');
      else setMessage('Camera could not start. Try again or enter the printed code.');
    } finally {
      starting = false;
      if (!submitting) button.disabled = false;
    }
  }

  button.addEventListener('click', () => { void startCamera(); });
  window.addEventListener('pagehide', stopCamera);
  document.addEventListener('visibilitychange', () => { if (document.hidden && scanning) stopCamera(); });
})();
