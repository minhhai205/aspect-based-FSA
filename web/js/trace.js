// Truy vết: từ một ô/điểm trên biểu đồ xuống từng câu gốc, tô sáng đúng đoạn target.

import { get, isAbort } from './api.js';
import { el, clear, fmtInt, fmtDate, fmtDateTime, highlight, SENT } from './util.js';

const PAGE = 20;
const safeUrl = (u) => (/^https?:\/\//i.test(u) ? u : null);

export function createTraceView({ root, state, meta, onState, onOpenArticle }) {
  const filtersEl = document.getElementById('trace-filters');
  const listEl = document.getElementById('trace-list');
  const countEl = document.getElementById('trace-count');
  const moreBtn = document.getElementById('trace-more');
  const status = root.querySelector(':scope > .status');
  let token = 0;
  let offset = 0;
  let total = 0;

  // --- thanh lọc, dựng một lần, đồng bộ lại mỗi lần refresh ---
  const tSel = el('select', { 'aria-label': 'Chủ thể' },
    el('option', { value: '', text: 'Tất cả chủ thể' }),
    meta.targets.map((t) => el('option', { value: t.id, text: t.id })));
  const aSel = el('select', { 'aria-label': 'Khía cạnh' },
    el('option', { value: '', text: 'Tất cả khía cạnh' }),
    meta.aspects.map((a) => el('option', { value: a.l2, text: a.l2 })));
  tSel.addEventListener('change', () => onState({ xTarget: tSel.value }));
  aSel.addEventListener('change', () => onState({ xAspect: aSel.value }));

  const segBtns = [['', 'Tất cả'], ['positive', '▲ Tích cực'], ['negative', '▼ Tiêu cực'], ['neutral', '● Trung tính']]
    .map(([v, t]) => el('button', { class: 'btn', type: 'button', 'data-v': v, text: t, onclick: () => onState({ xSent: v }) }));
  const seg = el('div', { class: 'seg', role: 'group', 'aria-label': 'Cảm xúc' }, segBtns);

  const dayTag = el('span', { class: 'tag', hidden: true });
  const clearBtn = el('button', {
    class: 'btn ghost', type: 'button', text: 'Xóa bộ lọc',
    onclick: () => onState({ xTarget: '', xAspect: '', xSent: '', xDay: '' }),
  });
  filtersEl.append(tSel, aSel, seg, dayTag, clearBtn);

  function syncFilters() {
    tSel.value = state.xTarget;
    aSel.value = state.xAspect;
    segBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === state.xSent)));
    dayTag.hidden = !state.xDay;
    if (state.xDay) {
      const [a, b = a] = state.xDay.split('..');
      clear(dayTag).append(a === b ? `Ngày ${fmtDate(a)}` : `${fmtDate(a)} → ${fmtDate(b)}`,
        el('button', { type: 'button', 'aria-label': 'Bỏ lọc ngày', text: '✕', onclick: () => onState({ xDay: '' }) }));
    }
    clearBtn.hidden = !(state.xTarget || state.xAspect || state.xSent || state.xDay);
  }

  function setStatus(msg, retry) {
    clear(status);
    if (!msg) return;
    status.append(msg);
    if (retry) status.append(el('button', { class: 'btn', type: 'button', text: 'Thử lại', onclick: retry }));
  }

  function item(i) {
    const s = SENT[i.sentiment];
    const isCopy = /~m\d+$/.test(i.doc_id);   // bản sao ngày giả của dữ liệu mẫu
    const href = safeUrl(i.url);
    return el('li', { class: 'titem', 'data-id': i.triplet_id },
      el('div', { class: 'tmeta' },
        el('span', { class: `pill ${s.cls}`, text: `${s.icon} ${s.label}` }),
        el('b', { text: i.canonical_id ?? i.target_text }),
        el('span', { text: i.aspect_l2 }),
        el('span', { text: fmtDateTime(i.published_at) }),
        el('span', { text: i.source_name }),
        isCopy ? el('span', { text: '· bản sao mẫu' }) : null),
      el('p', { class: 'tsent' }, highlight(i.text, [{ start: i.target_start, end: i.target_end }])),
      el('div', { class: 'tfoot' },
        el('button', { class: 'link', type: 'button', text: i.title, onclick: () => onOpenArticle(i.doc_id) }),
        href ? el('a', { href, target: '_blank', rel: 'noopener noreferrer', text: 'Mở bài gốc ↗' }) : null));
  }

  function dayRange() {
    if (!state.xDay) return { start: state.start, end: state.end };
    const [a, b = a] = state.xDay.split('..');
    return { start: a, end: b };
  }

  async function load(reset) {
    const my = ++token;
    if (reset) { offset = 0; clear(listEl); }
    moreBtn.disabled = true;
    setStatus(reset ? 'Đang tải…' : '');
    try {
      const r = await get('/api/trace', {
        target: state.xTarget, aspect: state.xAspect, sentiment: state.xSent,
        ...dayRange(),
        limit: PAGE, offset,
      }, { key: 'trace' });
      if (my !== token) return;
      total = r.total;
      setStatus('');
      if (!total) listEl.append(el('li', { class: 'empty-msg', text: 'Không có câu nào khớp bộ lọc.' }));
      r.items.forEach((i) => listEl.append(item(i)));
      offset += r.items.length;
      countEl.textContent = total ? `${fmtInt(Math.min(offset, total))} / ${fmtInt(total)} câu` : '';
      moreBtn.hidden = offset >= total;
      moreBtn.disabled = false;
    } catch (e) {
      if (isAbort(e) || my !== token) return;
      setStatus(`${e.message}.`, () => load(reset));
    }
  }

  moreBtn.addEventListener('click', () => load(false));

  return { refresh: () => { syncFilters(); return load(true); } };
}
