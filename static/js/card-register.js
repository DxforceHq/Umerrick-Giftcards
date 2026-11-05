(() => {
  const form = document.querySelector('.cards-filters');
  const toggle = form?.querySelector('.cards-filter-toggle');
  const fields = document.querySelector('#cards-advanced-filters');
  if (!form || !toggle || !fields) return;

  const mobile = window.matchMedia('(max-width: 600px)');
  let mobileExpanded = form.dataset.activeFilters === 'true';

  function updateButton() {
    const expanded = !fields.hidden;
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.setAttribute('aria-label', expanded ? 'Hide filters' : 'Show filters');
  }

  function syncLayout() {
    if (mobile.matches) {
      toggle.hidden = false;
      fields.hidden = !mobileExpanded;
    } else {
      toggle.hidden = true;
      fields.hidden = false;
    }
    updateButton();
  }

  toggle.addEventListener('click', () => {
    mobileExpanded = !mobileExpanded;
    fields.hidden = !mobileExpanded;
    updateButton();
  });
  mobile.addEventListener('change', syncLayout);
  syncLayout();
})();
