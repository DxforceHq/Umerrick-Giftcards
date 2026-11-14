(() => {
  const themeButtons = document.querySelectorAll('.theme-toggle');
  const updateThemeButtons = () => {
    const dark = document.documentElement.dataset.theme === 'dark';
    themeButtons.forEach(button => {
      const action = dark ? 'Switch to light mode' : 'Switch to dark mode';
      button.setAttribute('aria-label', action);
      button.setAttribute('title', action);
      button.setAttribute('aria-pressed', String(dark));
      button.querySelector('.theme-toggle-label').textContent = dark ? 'Light mode' : 'Dark mode';
    });
  };
  updateThemeButtons();
  themeButtons.forEach(button => button.addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme !== 'dark';
    if (dark) document.documentElement.dataset.theme = 'dark';
    else delete document.documentElement.dataset.theme;
    try { localStorage.setItem('umerrick-theme', dark ? 'dark' : 'light'); } catch (error) { /* Theme still works for this page. */ }
    updateThemeButtons();
  }));

  const refreshButton = document.querySelector('.app-refresh');
  refreshButton?.addEventListener('click', async () => {
    if (refreshButton.disabled) return;
    refreshButton.disabled = true;
    refreshButton.setAttribute('aria-label', 'Refreshing app');
    refreshButton.querySelector('span').textContent = 'Refreshing…';
    try {
      if ('serviceWorker' in navigator) {
        const registration = await navigator.serviceWorker.getRegistration();
        if (registration && navigator.onLine) {
          await Promise.race([registration.update(), new Promise(resolve => setTimeout(resolve, 2500))]);
        }
      }
    } catch (_) { /* Reload still checks the server when available. */ }
    window.location.reload();
  });

  if (document.body.classList.contains('app-page') && 'serviceWorker' in navigator && window.isSecureContext) {
    const priceAccess = document.body.dataset.canViewPrices === 'true';
    if (!priceAccess) { try { localStorage.removeItem('umerrick-price-list-v1'); } catch (_) {} }
    navigator.serviceWorker.register('/pwa/prices-worker.js', { scope: '/' })
      .then(() => navigator.serviceWorker.ready)
      .then(registration => registration.active?.postMessage({ type: priceAccess ? 'CACHE_PRICE_PAGE' : 'CLEAR_PRICE_PAGE' }))
      .catch(() => {});
  }

  const welcome = document.querySelector('#app-welcome');
  const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const installPanel = document.querySelector('#app-install');
  if (installPanel && !standalone) {
    const action = installPanel.querySelector('#app-install-action');
    const dismiss = installPanel.querySelector('#app-install-dismiss');
    const instructions = installPanel.querySelector('#app-install-instructions');
    const shell = document.querySelector('.app-shell');
    let installEvent = null;
    let previousFocus = null;
    const iphone = /iPhone|iPad|iPod/.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    instructions.textContent = iphone
      ? 'Tap Share in your browser, then Add to Home Screen.'
      : 'If Install app is unavailable, use your browser menu to add this site to your Home Screen.';
    const close = () => {
      installPanel.hidden = true;
      if (shell) shell.inert = false;
      previousFocus?.focus({preventScroll: true});
    };
    window.addEventListener('beforeinstallprompt', event => {
      event.preventDefault();
      installEvent = event;
      action.hidden = false;
      instructions.textContent = 'Install U_MERRICK for quick access from your Home Screen.';
    });
    window.addEventListener('appinstalled', close);
    action.addEventListener('click', async () => {
      if (!installEvent) return;
      const event = installEvent;
      installEvent = null;
      action.disabled = true;
      event.prompt();
      try { await event.userChoice; } catch (_) { /* The browser keeps control of installation. */ }
      close();
    });
    dismiss.addEventListener('click', close);
    installPanel.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key !== 'Tab') return;
      const buttons = [action, dismiss].filter(button => !button.hidden);
      if (event.shiftKey && document.activeElement === buttons[0]) {
        event.preventDefault(); buttons.at(-1).focus();
      } else if (!event.shiftKey && document.activeElement === buttons.at(-1)) {
        event.preventDefault(); buttons[0].focus();
      }
    });
    previousFocus = document.activeElement;
    installPanel.hidden = false;
    if (shell) shell.inert = true;
    dismiss.focus({preventScroll: true});
  }
  document.querySelectorAll('form[action$="/accounts/logout/"]').forEach(form => {
    form.addEventListener('submit', () => {
      try { sessionStorage.removeItem('umerrick-welcome-seen'); } catch (_) { /* Sign-out still proceeds. */ }
    });
  });
  if (welcome && standalone) {
    const key = 'umerrick-welcome-seen';
    let seen = false;
    try { seen = sessionStorage.getItem(key) === '1'; } catch (_) { /* Continue without session storage. */ }
    const shell = document.querySelector('.app-shell');
    const continueButton = welcome.querySelector('.app-welcome-continue');
    const showWelcome = () => {
      if (!welcome.hidden || !navigator.onLine) return;
      welcome.hidden = false;
      if (shell) shell.inert = true;
      continueButton.focus({ preventScroll: true });
    };
    continueButton.addEventListener('click', () => {
      try { sessionStorage.setItem(key, '1'); } catch (_) { /* Continue works without storage. */ }
      welcome.hidden = true;
      if (shell) shell.inert = false;
      document.querySelector('.menu-toggle')?.focus({ preventScroll: true });
    });
    if (!seen) showWelcome();
    let hiddenAt = 0;
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) hiddenAt = Date.now();
      else if (hiddenAt && Date.now() - hiddenAt >= 5 * 60 * 1000) showWelcome();
    });
  }

  document.querySelectorAll('.flash-close').forEach(button => {
    button.addEventListener('click', () => button.closest('.flash-message')?.remove());
  });
  document.querySelectorAll('.flash-message.success').forEach(message => {
    window.setTimeout(() => message.remove(), 3500);
  });

  const nativeDialog = document.querySelector('#app-confirm');
  const isIphoneSafari = /iPhone|iPod/.test(navigator.userAgent) &&
    /Safari/.test(navigator.userAgent) &&
    !/CriOS|FxiOS|EdgiOS|OPiOS/.test(navigator.userAgent);
  let dialog = nativeDialog;
  let overlay = null;
  if (nativeDialog && isIphoneSafari) {
    // Keep the same content and styling without Safari's native dialog layer.
    overlay = document.createElement('div');
    overlay.className = 'app-dialog-overlay';
    overlay.hidden = true;
    const panel = document.createElement('section');
    panel.className = 'app-dialog';
    panel.id = nativeDialog.id;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-labelledby', nativeDialog.getAttribute('aria-labelledby'));
    panel.setAttribute('aria-describedby', nativeDialog.getAttribute('aria-describedby'));
    while (nativeDialog.firstChild) panel.append(nativeDialog.firstChild);
    overlay.append(panel);
    nativeDialog.replaceWith(overlay);
    dialog = panel;
  }
  let confirmationPending = false;
  const afterTwoFrames = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const waitForSafariViewport = async keyboardWasVisible => {
    const viewport = window.visualViewport;
    if (keyboardWasVisible && viewport) {
      // Safari may update its touch coordinates only after the keyboard's viewport resize.
      await new Promise(resolve => {
        let quietTimer;
        const finish = () => {
          clearTimeout(timeout);
          clearTimeout(quietTimer);
          viewport.removeEventListener('resize', onResize);
          resolve();
        };
        const onResize = () => {
          clearTimeout(quietTimer);
          quietTimer = setTimeout(finish, 120);
        };
        viewport.addEventListener('resize', onResize);
        const timeout = setTimeout(finish, 750);
      });
    }
    await afterTwoFrames();
  };
  window.umerrickConfirm = ({title, description, details = [], confirmLabel = 'Confirm'}) => new Promise(resolve => {
    if (!dialog || (!overlay && typeof dialog.showModal !== 'function')) {
      resolve(window.confirm([title, description, ...details.map(([label, value]) => `${label}: ${value}`)].join('\n')));
      return;
    }
    if (confirmationPending || (overlay ? !overlay.hidden : dialog.open)) { resolve(false); return; }
    confirmationPending = true;
    const previousFocus = document.activeElement;
    const viewport = window.visualViewport;
    const layoutHeight = Math.max(window.innerHeight, document.documentElement.clientHeight);
    const keyboardWasVisible = !!(overlay && viewport && viewport.scale <= 1.05 && viewport.height < layoutHeight - 150);
    if (previousFocus instanceof HTMLElement && previousFocus.matches('input, textarea, select, [contenteditable="true"]')) previousFocus.blur();
    dialog.querySelector('#app-confirm-title').textContent = title;
    dialog.querySelector('#app-confirm-description').textContent = description;
    const list = dialog.querySelector('#app-confirm-details');
    list.replaceChildren();
    details.forEach(([label, value]) => {
      const term = document.createElement('dt');
      const definition = document.createElement('dd');
      term.textContent = label;
      definition.textContent = value;
      list.append(term, definition);
    });
    list.hidden = details.length === 0;
    const confirm = dialog.querySelector('[data-dialog-confirm]');
    const cancel = dialog.querySelector('[data-dialog-cancel]');
    if (!overlay) dialog.returnValue = '';
    confirm.textContent = confirmLabel;
    const shell = overlay ? document.querySelector('.app-shell') : null;
    const wasInert = shell?.inert ?? false;
    let positionFrame = null;
    const placeOverlay = () => {
      const viewport = window.visualViewport;
      overlay.style.top = `${viewport?.pageTop ?? window.scrollY}px`;
      overlay.style.left = `${viewport?.pageLeft ?? window.scrollX}px`;
      overlay.style.width = `${viewport?.width ?? window.innerWidth}px`;
      overlay.style.height = `${viewport?.height ?? window.innerHeight}px`;
    };
    const scheduleOverlayPosition = () => {
      if (positionFrame !== null) return;
      positionFrame = requestAnimationFrame(() => {
        positionFrame = null;
        if (!overlay.hidden) placeOverlay();
      });
    };
    let settled = false;
    const finish = value => {
      if (settled) return;
      settled = true;
      confirmationPending = false;
      confirm.onclick = null;
      cancel.onclick = null;
      if (overlay) {
        overlay.hidden = true;
        overlay.removeEventListener('keydown', onKeydown);
        window.removeEventListener('scroll', scheduleOverlayPosition);
        window.visualViewport?.removeEventListener('scroll', scheduleOverlayPosition);
        window.visualViewport?.removeEventListener('resize', scheduleOverlayPosition);
        if (positionFrame !== null) cancelAnimationFrame(positionFrame);
        if (shell) shell.inert = wasInert;
      }
      if (previousFocus?.isConnected && (value !== 'confirm' || !previousFocus.matches?.('input, textarea, select, [contenteditable="true"]'))) previousFocus.focus({preventScroll: true});
      resolve(value === 'confirm');
    };
    const close = value => {
      if (overlay) finish(value);
      else dialog.close(value);
    };
    const onKeydown = event => {
      if (event.key === 'Escape') { event.preventDefault(); close('cancel'); }
      if (event.key !== 'Tab') return;
      if (event.shiftKey && document.activeElement === cancel) { event.preventDefault(); confirm.focus(); }
      else if (!event.shiftKey && document.activeElement === confirm) { event.preventDefault(); cancel.focus(); }
    };
    confirm.onclick = () => close('confirm');
    cancel.onclick = () => close('cancel');
    const onNativeClose = () => finish(dialog.returnValue);
    if (!overlay) dialog.addEventListener('close', onNativeClose, {once: true});
    const show = () => {
      try {
        if (overlay) {
          placeOverlay();
          if (shell) shell.inert = true;
          overlay.hidden = false;
          overlay.addEventListener('keydown', onKeydown);
          window.addEventListener('scroll', scheduleOverlayPosition, {passive: true});
          window.visualViewport?.addEventListener('scroll', scheduleOverlayPosition, {passive: true});
          window.visualViewport?.addEventListener('resize', scheduleOverlayPosition, {passive: true});
          requestAnimationFrame(() => {
            if (!overlay.hidden) cancel.focus({preventScroll: true});
          });
        } else {
          dialog.showModal();
          cancel.focus({preventScroll: true});
        }
      } catch (error) {
        if (!overlay) dialog.removeEventListener('close', onNativeClose);
        finish('cancel');
      }
    };
    if (overlay) void waitForSafariViewport(keyboardWasVisible).then(show, () => finish('cancel'));
    else show();
  });

  const toggle = document.querySelector('.menu-toggle');
  const sidebar = document.querySelector('#app-sidebar');
  const backdrop = document.querySelector('.nav-backdrop');
  if (!toggle || !sidebar || !backdrop) return;
  const close = () => {
    sidebar.classList.remove('is-open');
    backdrop.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Open navigation');
  };
  toggle.addEventListener('click', () => {
    const open = !sidebar.classList.contains('is-open');
    sidebar.classList.toggle('is-open', open);
    backdrop.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
    if (open) sidebar.querySelector('.nav-link')?.focus();
  });
  backdrop.addEventListener('click', close);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
  window.addEventListener('resize', () => { if (window.innerWidth > 900) close(); });
})();
