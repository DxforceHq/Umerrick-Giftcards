(() => {
  const section = document.querySelector('#staff-performance');
  const search = document.querySelector('#staff-performance-query');
  if (!section || !search) return;

  const mobile = window.matchMedia('(max-width: 768px)');
  const applyLayout = () => { section.open = !mobile.matches; };
  applyLayout();
  mobile.addEventListener('change', applyLayout);

  const rows = [...section.querySelectorAll('.staff-performance-row')];
  const noMatch = document.querySelector('#staff-performance-no-match');
  search.addEventListener('input', () => {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    rows.forEach(row => {
      row.hidden = !row.dataset.searchName.includes(query);
      if (!row.hidden) visible += 1;
    });
    noMatch.hidden = !query || visible > 0;
  });
})();
