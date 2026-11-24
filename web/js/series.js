// Biểu đồ theo ngày: đường net sentiment + cột khối lượng xếp chồng theo cảm xúc.
// Dùng cho cả "theo chủ thể" (group = target) lẫn "theo khía cạnh" (group = aspect).

import { get, isAbort } from './api.js';
import { el, clear, fmtInt, fmtNet, fmtDay, fmtDate, theme, MIN_N } from './util.js';

const Y_WIDTH = 56;    // cố định bề rộng trục Y để hai biểu đồ xếp chồng thẳng hàng theo trục X
const MAX_SELECTED = 6;
export const WINDOW = 7;

/** Cửa sổ trượt w ngày. net gộp = (Σpos − Σneg) / Σn, KHÔNG phải trung bình các net hằng ngày:
 *  trung bình kiểu đó cho ngày 2 mẫu cùng trọng số với ngày 200 mẫu. */
function pool(points, w) {
  if (w <= 1) return points;
  return points.map((p, i) => {
    const seg = points.slice(Math.max(0, i - w + 1), i + 1);
    const f = (k) => seg.reduce((a, q) => a + q[k], 0);
    const n = f('n'), pos = f('pos'), neg = f('neg');
    return { day: p.day, n, pos, neg, neu: f('neu'), net: n ? (pos - neg) / n : null };
  });
}

export function createSeriesView({ root, group, state, meta, onPick, onState }) {
  const isTarget = group === 'target';
  const selKey = isTarget ? 'targets' : 'aspects';     // chuỗi đang chọn
  const filterKey = isTarget ? 'tAspect' : 'aTarget';  // bộ lọc chiều còn lại

  const chipsEl = root.querySelector('.chips');
  const select = root.querySelector('.f-select');
  const netCv = root.querySelector('.c-net');
  const volCv = root.querySelector('.c-vol');
  const status = root.querySelector('.chart-box .status');
  const caption = root.querySelector('.caption');
  root.querySelectorAll('.chart-box').forEach((b) => { b.style.height = `${b.dataset.h}px`; });

  let netChart = null;
  let volChart = null;
  let token = 0;

  // --- bộ lọc chiều còn lại ---
  const opts = isTarget
    ? [['', 'Tất cả khía cạnh'], ...meta.aspects.map((a) => [a.l2, a.l2])]
    : [['', 'Tất cả chủ thể'], ...meta.targets.slice(0, 40).map((t) => [t.id, t.id])];
  for (const [v, t] of opts) select.append(el('option', { value: v, text: t }));
  // Đổi bộ lọc thì bỏ lựa chọn thủ công: chuỗi đã chọn có thể không có tin trong bộ lọc mới,
  // để nguyên sẽ ra biểu đồ trống trong khi danh sách chip đã đổi sang thứ khác.
  select.addEventListener('change', () => onState({ [filterKey]: select.value, [selKey]: [] }));

  // --- nút chuyển cách gộp (dùng chung cho cả hai view) ---
  const winBtns = [['', `Gộp ${WINDOW} ngày`], ['1', 'Theo ngày']].map(([v, t]) =>
    el('button', { class: 'btn', type: 'button', 'data-v': v, text: t, onclick: () => onState({ win: v }) }));
  root.querySelector('.card-head').insertBefore(
    el('div', { class: 'seg', role: 'group', 'aria-label': 'Cách gộp theo thời gian' }, winBtns),
    root.querySelector('.filter'));

  const windowSize = () => (state.win === '1' ? 1 : WINDOW);
  function syncCaption() {
    const w = windowSize();
    winBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === state.win)));
    caption.textContent = (w > 1
      ? `Mỗi điểm gộp ${w} ngày gần nhất: net = (Σ tích cực − Σ tiêu cực) / Σ bộ ba. Cột bên dưới vẫn là số liệu từng ngày. `
      : 'Mỗi điểm là một ngày. ') +
      `Nét liền: từ ${MIN_N} bộ ba trở lên. Chấm rỗng và nét đứt: dưới ${MIN_N} bộ ba, ` +
      'dao động mạnh vì mẫu nhỏ, đừng diễn giải. Bấm vào một điểm để xem các câu gốc.';
  }

  function setStatus(msg, retry) {
    clear(status);
    if (!msg) return;
    status.append(msg);
    if (retry) status.append(el('button', { class: 'btn', type: 'button', text: 'Thử lại', onclick: retry }));
  }

  function renderChips(items, selected) {
    clear(chipsEl);
    const th = theme();
    const full = selected.length >= MAX_SELECTED;
    for (const it of items) {
      const idx = selected.indexOf(it.key);
      const on = idx >= 0;
      chipsEl.append(el('button', {
        class: 'chip', type: 'button', 'aria-pressed': String(on),
        disabled: !on && full,
        title: !on && full ? `Tối đa ${MAX_SELECTED} chuỗi cùng lúc` : null,
        onclick: () => {
          const next = on ? selected.filter((k) => k !== it.key) : [...selected, it.key];
          onState({ [selKey]: next });
        },
      },
      el('span', { class: 'sw', style: on ? `background:${th.series[idx]}` : '' }),
      it.key, el('span', { class: 'n', text: fmtInt(it.n) })));
    }
  }

  async function refresh() {
    const my = ++token;
    select.value = state[filterKey];
    syncCaption();
    setStatus('Đang tải…');
    try {
      const base = { start: state.start, end: state.end };
      let resp, items, selected;

      if (isTarget) {
        const pool = await get('/api/targets', { ...base, aspect: state.tAspect, limit: 12 }, { key: `pool-${group}` });
        if (my !== token) return;
        const ids = pool.map((p) => p.canonical_id);
        selected = (state.targets.length ? state.targets : ids.slice(0, 5)).slice(0, MAX_SELECTED);
        resp = await get('/api/series', { group, keys: selected, ...base, aspect: state.tAspect }, { key: `series-${group}` });
        if (my !== token) return;
        const nOf = new Map(pool.map((p) => [p.canonical_id, p.n]));
        resp.series.forEach((s) => { if (!nOf.has(s.key)) nOf.set(s.key, s.n); });
        items = [...new Set([...ids, ...selected])].map((k) => ({ key: k, n: nOf.get(k) ?? 0 }));
      } else {
        const all = meta.aspects.map((a) => a.l2);
        resp = await get('/api/series', { group, keys: all, ...base, target: state.aTarget }, { key: `series-${group}` });
        if (my !== token) return;
        const byN = [...resp.series].sort((a, b) => b.n - a.n);
        items = byN.map((s) => ({ key: s.key, n: s.n }));
        selected = (state.aspects.length ? state.aspects : byN.filter((s) => s.n > 0).slice(0, 5).map((s) => s.key))
          .slice(0, MAX_SELECTED);
      }

      renderChips(items, selected);
      const chosen = selected.map((k) => resp.series.find((s) => s.key === k)).filter(Boolean);
      if (!resp.all.n) {
        draw(null);
        setStatus('Không có bộ ba nào trong khoảng ngày và bộ lọc này.');
        return;
      }
      setStatus('');
      draw({ resp, chosen });
    } catch (e) {
      if (isAbort(e) || my !== token) return;
      draw(null);
      setStatus(`${e.message}.`, refresh);
    }
  }

  function draw(data) {
    netChart?.destroy(); volChart?.destroy();
    netChart = volChart = null;
    if (!data) return;
    const { resp, chosen } = data;
    const th = theme();
    const days = resp.all.points.map((p) => p.day);
    const labels = days.map(fmtDay);

    const common = {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      layout: { padding: { right: 6 } },
    };
    const xScale = (show) => ({
      grid: { display: false }, border: { color: th.gridStrong },
      ticks: { display: show, color: th.muted, maxTicksLimit: 10, maxRotation: 0 },
    });

    // --- đường net sentiment ---
    const w = windowSize();
    const datasets = chosen.map((s, i) => {
      const color = th.series[i];
      const pts = pool(s.points, w);
      const low = pts.map((p) => p.n < MIN_N);
      return {
        label: s.key, data: pts.map((p) => p.net), _key: s.key, _pts: pts,
        borderColor: color, backgroundColor: color, borderWidth: 2, tension: 0, spanGaps: false,
        pointRadius: 4, pointHoverRadius: 6, pointBorderWidth: 2, pointBorderColor: color,
        pointBackgroundColor: (c) => (low[c.dataIndex] ? th.surface : color),
        segment: { borderDash: (c) => (low[c.p0DataIndex] || low[c.p1DataIndex] ? [5, 4] : undefined) },
      };
    });

    netChart = new Chart(netCv, {
      type: 'line', data: { labels, datasets },
      options: {
        ...common,
        scales: {
          x: xScale(false),
          y: {
            min: -1, max: 1, border: { display: false },
            title: { display: true, text: 'Net sentiment', color: th.muted },
            ticks: { color: th.muted, stepSize: 0.5, callback: (v) => fmtNet(v) },
            grid: {
              color: (c) => (c.tick.value === 0 ? th.gridStrong : th.grid),
              lineWidth: (c) => (c.tick.value === 0 ? 2 : 1),
            },
            afterFit: (s) => { s.width = Y_WIDTH; },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (it) => fmtDate(days[it[0].dataIndex]) + (w > 1 ? ` · gộp ${w} ngày gần nhất` : ''),
              label: (c) => {
                const p = c.dataset._pts[c.dataIndex];
                if (!p.n) return `${c.dataset.label}: không có tin`;
                const thin = p.n < MIN_N ? ' · ít mẫu' : '';
                return `${c.dataset.label}: ${fmtNet(p.net)}  (n=${p.n}: ▲${p.pos} ●${p.neu} ▼${p.neg})${thin}`;
              },
            },
          },
        },
        onClick: (evt, _els, chart) => {
          const hit = chart.getElementsAtEventForMode(evt, 'nearest', { intersect: false }, true)[0];
          if (!hit) return;
          // điểm gộp w ngày đại diện cả cửa sổ, nên truy vết cũng phải lọc đúng cửa sổ đó
          const from = days[Math.max(0, hit.index - w + 1)];
          const to = days[hit.index];
          onPick({ group, key: chart.data.datasets[hit.datasetIndex]._key, day: from === to ? to : `${from}..${to}` });
        },
      },
    });

    // --- cột khối lượng: tổng các chuỗi đang chọn, xếp chồng theo cảm xúc ---
    const src = chosen.length ? chosen.map((s) => s.points) : [resp.all.points];
    const sum = (f) => days.map((_, i) => src.reduce((a, pts) => a + pts[i][f], 0));
    volChart = new Chart(volCv, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Tích cực', data: sum('pos'), backgroundColor: th.pos },
          { label: 'Trung tính', data: sum('neu'), backgroundColor: th.neu },
          { label: 'Tiêu cực', data: sum('neg'), backgroundColor: th.neg },
        ],
      },
      options: {
        ...common,
        scales: {
          x: { ...xScale(true), stacked: true },
          y: {
            stacked: true, beginAtZero: true, border: { display: false },
            title: { display: true, text: 'Số bộ ba', color: th.muted },
            ticks: { color: th.muted, precision: 0, maxTicksLimit: 4 },
            grid: { color: th.grid },
            afterFit: (s) => { s.width = Y_WIDTH; },
          },
        },
        plugins: {
          legend: { position: 'top', align: 'end', labels: { color: th.muted, boxWidth: 10, boxHeight: 10 } },
          tooltip: { callbacks: { title: (it) => fmtDate(days[it[0].dataIndex]) } },
        },
      },
    });
  }

  return { refresh };
}
