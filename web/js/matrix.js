// Ma trận nhiệt chủ thể × khía cạnh. Dựng bằng bảng HTML (không dùng canvas) để mỗi ô
// bấm được, đọc được bằng bàn phím và trình đọc màn hình.

import { get, isAbort } from './api.js';
import { el, clear, fmtNet, fmtInt, MATRIX_MIN_N, MATRIX_FULL_N } from './util.js';

export function createMatrixView({ root, state, meta, onPick }) {
  const host = root.querySelector('.matrix-host');
  const status = root.querySelector('.status');
  const legend = document.getElementById('matrix-legend');
  let token = 0;

  legend.append(
    el('span', {}, 'Màu = net: ', el('span', { class: 'grad' }), ' −1 → 0 → +1'),
    el('span', {}, 'Ô nhạt = ít mẫu (đạt độ đậm tối đa từ n=', String(MATRIX_FULL_N), ')'),
    el('span', {}, el('span', { class: 'hatch' }), ` Ô sọc = dưới ${MATRIX_MIN_N} bộ ba, chưa đáng tin`),
    el('span', {}, 'Ô gạch chéo mờ = không có bộ ba'),
  );

  function setStatus(msg, retry) {
    clear(status);
    if (!msg) return;
    status.append(msg);
    if (retry) status.append(el('button', { class: 'btn', type: 'button', text: 'Thử lại', onclick: retry }));
  }

  async function refresh() {
    const my = ++token;
    setStatus('Đang tải…');
    try {
      const r = await get('/api/matrix', { start: state.start, end: state.end, top: 12 }, { key: 'matrix' });
      if (my !== token) return;
      if (!r.cells.length) {
        clear(host);
        setStatus('Không có bộ ba nào trong khoảng ngày này.');
        return;
      }
      setStatus('');
      render(r);
    } catch (e) {
      if (isAbort(e) || my !== token) return;
      clear(host);
      setStatus(`${e.message}.`, refresh);
    }
  }

  function render(r) {
    const cell = new Map(r.cells.map((c) => [`${c.canonical_id}|${c.aspect_l2}`, c]));
    const l1Of = new Map(meta.aspects.map((a) => [a.l2, a.l1]));
    const total = new Map();
    r.cells.forEach((c) => total.set(c.canonical_id, (total.get(c.canonical_id) ?? 0) + c.n));

    // hàng nhóm cấp 1: gộp các cột liền nhau cùng cấp 1
    const groups = [];
    for (const a of r.aspects) {
      const l1 = l1Of.get(a);
      if (groups.at(-1)?.l1 === l1) groups.at(-1).span++;
      else groups.push({ l1, span: 1 });
    }

    const thead = el('thead', {},
      el('tr', {}, el('td'), groups.map((g) => el('th', { class: 'l1', colspan: g.span, text: g.l1 }))),
      el('tr', {}, el('td'), r.aspects.map((a) => el('th', { class: 'col', scope: 'col' }, el('span', { text: a })))));

    const tbody = el('tbody', {}, r.targets.map((t) => el('tr', {},
      el('th', { class: 'row', scope: 'row' },
        el('button', { type: 'button', title: `Xem câu gốc của ${t}`, text: t, onclick: () => onPick({ target: t }) }),
        el('div', { class: 'm', style: 'font-size:10px;color:var(--muted)', text: `n=${fmtInt(total.get(t) ?? 0)}` })),
      r.aspects.map((a) => cellEl(t, a, cell.get(`${t}|${a}`))))));

    clear(host).append(el('table', { class: 'matrix' }, thead, tbody));
  }

  function cellEl(t, a, c) {
    if (!c || !c.n) return el('td', { class: 'cell empty', 'aria-label': `${t} × ${a}: không có bộ ba` }, '');
    const conf = Math.min(1, c.n / MATRIX_FULL_N);
    const mix = Math.round(60 * Math.min(1, Math.abs(c.net)) * conf);   // tối đa 60% để chữ vẫn đọc được
    const color = c.net >= 0 ? 'var(--pos)' : 'var(--neg)';
    const label = `${t} × ${a}: net ${fmtNet(c.net)}, n=${c.n} (▲${c.pos} ●${c.neu} ▼${c.neg})` +
      (c.n < MATRIX_MIN_N ? ' — quá ít mẫu' : '');
    return el('td', {
      class: `cell${c.n < MATRIX_MIN_N ? ' thin' : ''}`,
      style: `background:color-mix(in srgb, ${color} ${mix}%, var(--surface))`,
    }, el('button', {
      type: 'button', title: label, 'aria-label': label,
      onclick: () => onPick({ target: t, aspect: a }),
    }, el('span', { class: 'v', text: fmtNet(c.net) }), el('span', { class: 'm', text: `n=${c.n}` })));
  }

  return { refresh };
}
