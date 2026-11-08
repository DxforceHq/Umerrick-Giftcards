(() => {
  document.querySelectorAll('input[type="password"]').forEach((input, index) => {
    if (!input.id) input.id = `password-input-${index}`;

    const wrapper = document.createElement('span');
    wrapper.className = 'password-field';
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'password-visibility-toggle';
    toggle.setAttribute('aria-controls', input.id);
    toggle.setAttribute('aria-label', 'Show password');
    toggle.setAttribute('aria-pressed', 'false');
    toggle.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/><path class="password-eye-slash" d="m3 21 18-18"/></svg>';
    toggle.addEventListener('click', () => {
      const showing = input.type === 'password';
      input.type = showing ? 'text' : 'password';
      toggle.setAttribute('aria-label', showing ? 'Hide password' : 'Show password');
      toggle.setAttribute('aria-pressed', String(showing));
      input.focus({ preventScroll: true });
    });
    wrapper.appendChild(toggle);
  });
})();
