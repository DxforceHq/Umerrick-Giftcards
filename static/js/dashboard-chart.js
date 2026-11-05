(() => {
  const source = document.querySelector('#activity-chart-data');
  const host = document.querySelector('#activity-chart');
  const rows = document.querySelector('#chart-values');
  const empty = document.querySelector('#chart-empty');
  const period = document.querySelector('#period-select');
  const custom = document.querySelector('#custom-range');
  if (period && custom) {
    const update = () => {
      custom.hidden = period.value !== 'custom';
      custom.querySelectorAll('input').forEach(input => { input.required = !custom.hidden; });
    };
    period.addEventListener('change', update);
    update();
  }
  if (!source || !host || !rows || !empty) return;
  const data = JSON.parse(source.textContent);
  const names = ['issued', 'activated', 'redeemed'];
  data.labels.forEach((label, i) => {
    const row = document.createElement('tr');
    [label, ...names.map(name => String(data[name][i]))].forEach(value => {
      const cell = document.createElement('td');
      cell.textContent = value;
      row.appendChild(cell);
    });
    rows.appendChild(row);
  });
  const maximum = Math.max(0, ...names.flatMap(name => data[name]));
  empty.hidden = maximum > 0;
  if (!maximum) return;

  const svgNS = 'http://www.w3.org/2000/svg';
  const element = (tag, attributes = {}) => {
    const node = document.createElementNS(svgNS, tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  };
  const render = () => {
    const width = Math.max(260, host.clientWidth);
    const height = width < 500 ? 230 : 280;
    const margins = {left: 35, right: 13, top: 14, bottom: 33};
    const plotWidth = width - margins.left - margins.right;
    const plotHeight = height - margins.top - margins.bottom;
    const top = maximum <= 4 ? 4 : Math.ceil(maximum / 4) * 4;
    const x = index => margins.left + (data.labels.length === 1 ? plotWidth / 2 : index * plotWidth / (data.labels.length - 1));
    const y = value => margins.top + plotHeight * (1 - value / top);
    const styles = getComputedStyle(host);
    const muted = styles.getPropertyValue('--chart-muted').trim() || '#6E685F';
    const grid = styles.getPropertyValue('--chart-grid').trim() || '#E7E2D8';
    const svg = element('svg', {viewBox: `0 0 ${width} ${height}`, width: '100%', height, 'aria-hidden': 'true'});
    for (let step = 0; step <= 4; step++) {
      const value = top * step / 4;
      svg.appendChild(element('line', {x1: margins.left, x2: width - margins.right, y1: y(value), y2: y(value), stroke: grid, 'stroke-width': 1}));
      const label = element('text', {x: margins.left - 9, y: y(value) + 4, 'text-anchor': 'end', fill: muted, 'font-size': 11});
      label.textContent = Number.isInteger(value) ? String(value) : value.toFixed(1);
      svg.appendChild(label);
    }
    const tickCount = width < 500 ? 3 : 5;
    const tickIndexes = [...new Set(Array.from({length: Math.min(tickCount, data.labels.length)}, (_, i) =>
      Math.round(i * (data.labels.length - 1) / Math.max(1, Math.min(tickCount, data.labels.length) - 1))))];
    tickIndexes.forEach(index => {
      const label = element('text', {x: x(index), y: height - 9, 'text-anchor': index === 0 ? 'start' : index === data.labels.length - 1 ? 'end' : 'middle', fill: muted, 'font-size': 11});
      label.textContent = data.labels[index];
      svg.appendChild(label);
    });
    names.forEach(name => {
      const color = styles.getPropertyValue(`--chart-${name}`).trim();
      const points = data[name].map((value, i) => `${x(i)},${y(value)}`).join(' ');
      svg.appendChild(element('polyline', {points, fill: 'none', stroke: color, 'stroke-width': 2.5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'vector-effect': 'non-scaling-stroke'}));
      if (data.labels.length <= 32) data[name].forEach((value, i) => {
        const circle = element('circle', {cx: x(i), cy: y(value), r: 3.5, fill: color});
        const title = element('title');
        title.textContent = `${data.labels[i]}: ${value} ${name}`;
        circle.appendChild(title);
        svg.appendChild(circle);
      });
    });
    host.replaceChildren(svg);
  };
  render();
  if ('ResizeObserver' in window) new ResizeObserver(render).observe(host);
  else window.addEventListener('resize', render);
})();
