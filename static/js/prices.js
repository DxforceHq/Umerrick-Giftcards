(() => {
  const config = JSON.parse(document.querySelector('#price-config').textContent);
  const list = document.querySelector('#price-staff-list');
  const search = document.querySelector('#price-search');
  const status = document.querySelector('#price-sync');
  const empty = document.querySelector('#price-search-empty');
  const key = 'umerrick-price-list-v1';
  const dateText = value => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'unknown' : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  };
  const money = value => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN' }).format(value);
  function render(items) {
    if (!list) return;
    list.replaceChildren();
    if (!items.length) {
      const node = document.createElement('div'); node.className = 'empty';
      node.textContent = 'No active items are available.'; list.append(node); return;
    }
    for (const item of items) {
      const row = document.createElement('article'); row.className = 'price-row';
      row.dataset.priceName = item.name.toLocaleLowerCase();
      const details = document.createElement('div');
      const name = document.createElement('strong'); name.textContent = item.name;
      const updated = document.createElement('small'); updated.textContent = `Price updated ${dateText(item.updated_at)}`;
      const price = document.createElement('b'); price.textContent = money(item.price);
      details.append(name, updated); row.append(details, price); list.append(row);
    }
    filter();
  }
  function filter() {
    const term = search.value.trim().toLocaleLowerCase();
    let shown = 0;
    document.querySelectorAll('#price-admin-list [data-price-name], #price-staff-list [data-price-name]').forEach(row => {
      row.hidden = !row.dataset.priceName.includes(term);
      if (row.hidden && row.classList.contains('price-admin-item')) {
        row.querySelector('.price-inline-editor').hidden = true;
        row.querySelector('.price-admin-summary').setAttribute('aria-expanded', 'false');
      }
      if (!row.hidden) shown++;
    });
    empty.hidden = shown !== 0 || !term;
  }
  search.addEventListener('input', filter);
  const addAnother = document.querySelector('#price-add-another');
  const addRows = document.querySelector('#price-add-rows');
  const addToggle = document.querySelector('#price-add-toggle');
  const addContent = document.querySelector('#price-add-content');
  addToggle?.addEventListener('click', () => {
    addContent.hidden = !addContent.hidden;
    addToggle.setAttribute('aria-expanded', String(!addContent.hidden));
    addToggle.textContent = addContent.hidden ? 'Add items' : 'Close add form';
    if (!addContent.hidden) addContent.querySelector('input[name="name"]').focus();
  });
  addAnother?.addEventListener('click', () => {
    if (addRows.children.length >= 100) return;
    const row = document.querySelector('#price-add-row-template').content.firstElementChild.cloneNode(true);
    addRows.append(row);
    row.querySelector('input[name="name"]').focus();
    if (addRows.children.length >= 100) addAnother.disabled = true;
  });
  addRows?.addEventListener('click', event => {
    if (!event.target.matches('.price-remove-row')) return;
    event.target.closest('.price-add-row').remove();
    addAnother.disabled = false;
  });

  const adminList = document.querySelector('#price-admin-list');
  adminList?.addEventListener('click', event => {
    if (event.target.closest('form')) return;
    const summary = event.target.closest('.price-admin-summary');
    if (!summary) return;
    const row = summary.closest('.price-admin-item');
    const editor = row.querySelector('.price-inline-editor');
    document.querySelectorAll('.price-inline-editor').forEach(other => {
      if (other !== editor) other.hidden = true;
    });
    document.querySelectorAll('.price-admin-summary').forEach(other => {
      if (other !== summary) other.setAttribute('aria-expanded', 'false');
    });
    editor.hidden = !editor.hidden;
    summary.setAttribute('aria-expanded', String(!editor.hidden));
    if (!editor.hidden) editor.querySelector('input[name="price"]')?.focus();
  });
  let saved;
  try { saved = JSON.parse(localStorage.getItem(key) || 'null'); } catch (_) { saved = null; }
  if (config.staff && saved && Array.isArray(saved.items)) {
    render(saved.items);
    status.textContent = `Saved prices · Last synced ${dateText(saved.synced_at)}`;
  }
  async function sync() {
    try {
      const response = await fetch(config.dataUrl, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } });
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw Error('Unavailable');
      const data = await response.json();
      if (!Array.isArray(data.items)) throw Error('Invalid data');
      localStorage.setItem(key, JSON.stringify(data));
      saved = data;
      if (config.staff) render(data.items);
      status.textContent = `Up to date · Last synced ${dateText(data.synced_at)}`;
    } catch (_) {
      status.textContent = saved ? `Offline saved prices · Last synced ${dateText(saved.synced_at)}` : 'Offline · Open this list online once to save prices';
    }
  }
  sync();
  window.addEventListener('online', sync);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && navigator.onLine) sync(); });
  window.setInterval(() => { if (!document.hidden && navigator.onLine) sync(); }, 60000);
  if (config.staff && 'serviceWorker' in navigator && window.isSecureContext) {
    navigator.serviceWorker.register('/pwa/prices-worker.js', { scope: '/' })
      .then(() => navigator.serviceWorker.ready)
      .then(registration => registration.active?.postMessage({ type: 'CACHE_PRICE_PAGE' }))
      .catch(() => {});
  }
})();
