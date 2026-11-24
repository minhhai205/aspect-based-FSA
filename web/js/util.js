// Tiện ích dùng chung: định dạng số, dựng DOM, đọc màu theo giao diện sáng/tối.

export const MIN_N = 5;          // dưới ngưỡng này, một điểm trên đường bị coi là ít mẫu
export const MATRIX_MIN_N = 3;   // dưới ngưỡng này, ô ma trận bị gạch sọc
export const MATRIX_FULL_N = 8;  // từ ngưỡng này ô mới đạt độ đậm tối đa

const nf = new Intl.NumberFormat('vi-VN');
const nf2 = new Intl.NumberFormat('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const fmtInt = (n) => nf.format(n);

/** net sentiment có dấu, 2 chữ số: +0,33 / −0,12 / 0,00 ; null -> "–" */
export function fmtNet(v) {
  if (v == null) return '–';
  const r = Math.round(v * 100) / 100;
  return (r > 0 ? '+' : r < 0 ? '−' : '') + nf2.format(Math.abs(r));
}

export const fmtDay = (d) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;
export const fmtDate = (d) => `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}`;

export function fmtDateTime(iso) {
  return new Date(iso).toLocaleString('vi-VN', {
    timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export const SENT = {
  positive: { cls: 'pos', label: 'Tích cực', icon: '▲' },
  negative: { cls: 'neg', label: 'Tiêu cực', icon: '▼' },
  neutral: { cls: 'neu', label: 'Trung tính', icon: '●' },
};

/** Dựng phần tử DOM. Văn bản luôn đi qua textContent nên không có nguy cơ chèn HTML. */
export function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k === 'style') n.style.cssText = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) n.append(c);
  return n;
}

export const clear = (node) => { node.replaceChildren(); return node; };

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/** Màu cho Chart.js, đọc từ biến CSS để tự theo chế độ sáng/tối. */
export function theme() {
  return {
    text: cssVar('--text'), muted: cssVar('--muted'),
    grid: cssVar('--grid'), gridStrong: cssVar('--grid-strong'),
    pos: cssVar('--pos'), neg: cssVar('--neg'), neu: cssVar('--neu'),
    surface: cssVar('--surface'),
    series: [1, 2, 3, 4, 5, 6].map((i) => cssVar(`--s${i}`)),
  };
}

/**
 * Tô sáng các đoạn [start, end) trong text. Offset từ API là chỉ số KÝ TỰ Unicode
 * (code point, như Python), còn chuỗi JS đánh chỉ số theo UTF-16, nên phải tách
 * theo code point trước, nếu không sẽ lệch khi trước đó có emoji hay ký tự ngoài BMP.
 */
export function highlight(text, spans) {
  const cps = [...text];
  const frag = document.createDocumentFragment();
  let pos = 0;
  const sorted = [...spans].sort((a, b) => a.start - b.start || b.end - a.end);
  for (const s of sorted) {
    if (s.start < pos || s.end > cps.length || s.end <= s.start) continue; // bỏ đoạn chồng lấn
    if (s.start > pos) frag.append(cps.slice(pos, s.start).join(''));
    frag.append(el('mark', { class: 'span', text: cps.slice(s.start, s.end).join('') }));
    pos = s.end;
  }
  if (pos < cps.length) frag.append(cps.slice(pos).join(''));
  return frag;
}

export const addDays = (iso, k) => {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + k);
  return d.toISOString().slice(0, 10);
};
