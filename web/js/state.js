// Trạng thái giao diện, lưu trên URL hash để chia sẻ được và bấm Back/Forward được.

const MAP = {
  s: 'start', e: 'end', t: 'targets', a: 'aspects', tt: 'tAspect', at: 'aTarget',
  xt: 'xTarget', xa: 'xAspect', xs: 'xSent', xd: 'xDay', doc: 'doc', win: 'win',
};
const LISTS = new Set(['targets', 'aspects']);

export const state = {
  start: '', end: '', targets: [], aspects: [],
  tAspect: '', aTarget: '', xTarget: '', xAspect: '', xSent: '', xDay: '', doc: '',
  win: '',   // '' = mặc định gộp 7 ngày, '1' = theo ngày
};

export function loadHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  for (const [short, key] of Object.entries(MAP)) {
    const v = p.get(short) ?? '';
    state[key] = LISTS.has(key) ? (v ? v.split('|') : []) : v;
  }
}

export function saveHash() {
  const p = new URLSearchParams();
  for (const [short, key] of Object.entries(MAP)) {
    const v = state[key];
    const s = LISTS.has(key) ? v.join('|') : v;
    if (s) p.set(short, s);
  }
  const h = p.toString();
  history.replaceState(null, '', h ? `#${h}` : location.pathname + location.search);
}
