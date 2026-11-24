// Điều phối: tải meta, dựng bốn view, giữ trạng thái trên URL hash.

import { get, isAbort } from './api.js';
import { state, loadHash, saveHash } from './state.js';
import { el, clear, fmtInt, fmtNet, fmtDate, fmtDateTime, highlight, addDays, SENT } from './util.js';
import { createSeriesView } from './series.js';
import { createMatrixView } from './matrix.js';
import { createTraceView } from './trace.js';

const $ = (id) => document.getElementById(id);

function showNotice(...kids) {
  $('content').hidden = true;
  const n = $('notice');
  n.hidden = false;
  clear(n).append(...kids);
}

async function main() {
  let meta;
  try {
    meta = await get('/api/meta');
  } catch (e) {
    return showNotice(`${e.message}. Chạy `, el('code', { text: './absa serve' }), ' rồi tải lại trang.');
  }

  if (meta.is_mock) {
    const b = $('banner');
    b.hidden = false;
    b.textContent = 'DỮ LIỆU MẪU — nhãn do luật từ khóa gán, KHÔNG phải kết quả của model. Chỉ dùng để thử giao diện.';
  }
  if (!meta.triplets) {
    return showNotice(`Chưa có bộ ba nào trong ${meta.db}. Chạy `, el('code', { text: './absa mock' }),
      ' để sinh dữ liệu mẫu, hoặc ghép model rồi trỏ ', el('code', { text: 'ABSA_WEB_DB' }), ' sang ',
      el('code', { text: 'data/absa.db' }), '.');
  }

  // ---------------- khoảng ngày ----------------
  loadHash();
  const clampDay = (d, fb) => (d && d >= meta.start && d <= meta.end ? d : fb);
  state.start = clampDay(state.start, meta.start);
  state.end = clampDay(state.end, meta.end);
  if (state.start > state.end) [state.start, state.end] = [state.end, state.start];

  // URL do người dùng sửa tay có thể chứa giá trị rác: loại bỏ ở đây thay vì gửi lên API rồi nhận 422.
  const validT = new Set(meta.targets.map((t) => t.id));
  const validA = new Set(meta.aspects.map((a) => a.l2));
  const pick = (v, set) => (set.has(v) ? v : '');
  function sanitize() {
    state.targets = state.targets.filter((t) => validT.has(t));
    state.aspects = state.aspects.filter((a) => validA.has(a));
    state.tAspect = pick(state.tAspect, validA);  state.xAspect = pick(state.xAspect, validA);
    state.aTarget = pick(state.aTarget, validT);  state.xTarget = pick(state.xTarget, validT);
    state.xSent = pick(state.xSent, new Set(Object.keys(SENT)));
    if (!/^\d{4}-\d\d-\d\d(\.\.\d{4}-\d\d-\d\d)?$/.test(state.xDay)) state.xDay = '';
    if (state.win !== '1') state.win = '';
  }
  sanitize();

  const startIn = $('start'), endIn = $('end');
  for (const i of [startIn, endIn]) { i.min = meta.start; i.max = meta.end; }

  const QUICK = [[7, '7 ngày'], [14, '14 ngày'], [30, '30 ngày'], [0, 'Tất cả']];
  const quickBtns = QUICK.map(([n, t]) => el('button', {
    class: 'btn', type: 'button', text: t, 'data-n': n,
    onclick: () => setRange(n ? (addDays(meta.end, -(n - 1)) < meta.start ? meta.start : addDays(meta.end, -(n - 1))) : meta.start, meta.end),
  }));
  $('quick').append(...quickBtns);

  function syncRange() {
    startIn.value = state.start;
    endIn.value = state.end;
    for (const b of quickBtns) {
      const n = Number(b.dataset.n);
      const s = n ? (addDays(meta.end, -(n - 1)) < meta.start ? meta.start : addDays(meta.end, -(n - 1))) : meta.start;
      b.setAttribute('aria-pressed', String(state.start === s && state.end === meta.end));
    }
  }

  function setRange(start, end) {
    if (start > end) end = start;
    Object.assign(state, { start, end, xDay: '' });
    saveHash();
    syncRange();
    refreshAll();
  }
  startIn.addEventListener('change', () => startIn.value && setRange(startIn.value, state.end < startIn.value ? startIn.value : state.end));
  endIn.addEventListener('change', () => endIn.value && setRange(state.start > endIn.value ? endIn.value : state.start, endIn.value));

  // ---------------- các view ----------------
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const patch = (p) => { Object.assign(state, p); saveHash(); };

  function pickTrace(p) {
    patch(p);
    trace.refresh();
    $('v-trace').scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
  }

  const targetView = createSeriesView({
    root: $('v-target'), group: 'target', state, meta,
    onState: (p) => { patch(p); 'win' in p ? refreshSeries() : targetView.refresh(); },
    onPick: ({ key, day }) => pickTrace({ xTarget: key, xAspect: state.tAspect, xDay: day, xSent: '' }),
  });
  const aspectView = createSeriesView({
    root: $('v-aspect'), group: 'aspect', state, meta,
    onState: (p) => { patch(p); 'win' in p ? refreshSeries() : aspectView.refresh(); },
    onPick: ({ key, day }) => pickTrace({ xAspect: key, xTarget: state.aTarget, xDay: day, xSent: '' }),
  });
  const refreshSeries = () => { targetView.refresh(); aspectView.refresh(); };
  const matrixView = createMatrixView({
    root: $('v-matrix'), state, meta,
    onPick: ({ target = '', aspect = '' }) => pickTrace({ xTarget: target, xAspect: aspect, xDay: '', xSent: '' }),
  });
  const trace = createTraceView({
    root: $('v-trace'), state, meta,
    onState: (p) => { patch(p); trace.refresh(); },
    onOpenArticle: (doc) => openArticle(doc),
  });

  // ---------------- chỉ số tổng quan ----------------
  async function refreshKpis() {
    const box = clear($('kpis'));
    try {
      const [s, tg] = await Promise.all([
        get('/api/series', { group: 'target', top: 1, start: state.start, end: state.end }, { key: 'kpi-s' }),
        get('/api/targets', { start: state.start, end: state.end, limit: 200 }, { key: 'kpi-t' }),
      ]);
      const pts = s.all.points;
      const sum = (f) => pts.reduce((a, p) => a + p[f], 0);
      const n = sum('n'), pos = sum('pos'), neg = sum('neg'), neu = sum('neu');
      const net = n ? (pos - neg) / n : null;
      const withData = pts.filter((p) => p.n > 0).length;
      const pct = (v) => (n ? (100 * v) / n : 0).toFixed(1);

      box.append(
        tile('Bộ ba trong kỳ', fmtInt(n), `${pts.length} ngày, ${withData} ngày có dữ liệu`),
        tile('Net toàn kỳ', fmtNet(net), `▲${fmtInt(pos)}  ●${fmtInt(neu)}  ▼${fmtInt(neg)}`,
          net > 0 ? 'pos' : net < 0 ? 'neg' : '',
          el('div', { class: 'mix', role: 'img', 'aria-label': `Tích cực ${pct(pos)}%, trung tính ${pct(neu)}%, tiêu cực ${pct(neg)}%` },
            el('i', { class: 'p', style: `width:${pct(pos)}%` }),
            el('i', { class: 'u', style: `width:${pct(neu)}%` }),
            el('i', { class: 'g', style: `width:${pct(neg)}%` }))),
        tile('Chủ thể có tin', fmtInt(tg.length), 'đã chuẩn hóa về mã'),
        tile('Bộ ba mỗi ngày', withData ? fmtInt(Math.round(n / withData)) : '–', 'trung bình, tính các ngày có dữ liệu'),
      );
    } catch (e) {
      if (!isAbort(e)) box.append(el('div', { class: 'tile' }, el('div', { class: 'label', text: 'Tổng quan' }), el('div', { class: 'hint', text: e.message })));
    }
  }
  const tile = (label, value, hint, cls = '', extra = null) => el('div', { class: 'tile' },
    el('div', { class: 'label', text: label }),
    el('div', { class: `value ${cls}`, text: value }),
    el('div', { class: 'hint', text: hint }), extra);

  function refreshAll() {
    refreshKpis();
    targetView.refresh();
    aspectView.refresh();
    matrixView.refresh();
    trace.refresh();
  }

  // ---------------- hộp thoại bài báo ----------------
  const dlg = $('article');
  async function openArticle(doc) {
    patch({ doc });
    try {
      const a = await get(`/api/article/${encodeURIComponent(doc)}`, {}, { key: 'article' });
      $('article-title').textContent = a.title;
      const meta2 = $('article-meta');
      clear(meta2).append(`${a.source_name} · ${a.published_at ? fmtDateTime(a.published_at) : ''} · `,
        /^https?:\/\//i.test(a.url) ? el('a', { href: a.url, target: '_blank', rel: 'noopener noreferrer', text: 'Mở bài gốc ↗' }) : '');
      const body = clear($('article-body'));
      for (const s of a.sentences) {
        const spans = s.triplets.map((t) => ({ start: t.target_start, end: t.target_end }));
        body.append(el('div', { class: `asent${s.is_title ? ' title' : ''}` },
          el('div', {}, highlight(s.text, spans)),
          s.triplets.length ? el('div', { class: 'tags' }, s.triplets.map((t) => {
            const m = SENT[t.sentiment];
            return el('span', { class: `pill ${m.cls}`, title: t.aspect_l1, text: `${m.icon} ${t.canonical_id ?? t.target_text} · ${t.aspect_l2}` });
          })) : null));
      }
      if (!dlg.open) dlg.showModal();
    } catch (e) {
      if (!isAbort(e)) { patch({ doc: '' }); alert(`Không mở được bài: ${e.message}`); }
    }
  }
  $('article-close').addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener('close', () => patch({ doc: '' }));

  // ---------------- khởi động ----------------
  window.addEventListener('hashchange', () => {   // sửa URL tay hoặc bấm Back/Forward
    loadHash();
    sanitize();
    state.start = clampDay(state.start, meta.start);
    state.end = clampDay(state.end, meta.end);
    saveHash();   // ghi lại bản đã làm sạch để thanh địa chỉ không giữ giá trị rác
    syncRange();
    refreshAll();
    if (state.doc) openArticle(state.doc); else if (dlg.open) dlg.close();
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    targetView.refresh(); aspectView.refresh();
  });

  syncRange();
  saveHash();
  refreshAll();
  if (state.doc) openArticle(state.doc);
  document.documentElement.dataset.ready = '1';
}

main();
