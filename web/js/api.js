// Gọi API. Mỗi `key` chỉ cho phép một yêu cầu đang bay: gọi lại cùng key sẽ huỷ yêu cầu cũ,
// nên bấm liên tục không làm kết quả cũ về sau ghi đè kết quả mới.

export class ApiError extends Error {}

const inflight = new Map();

export async function get(path, params = {}, { key } = {}) {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === '') continue;
    if (Array.isArray(v)) v.forEach((x) => qs.append(k, x));
    else qs.set(k, v);
  }
  const ctl = new AbortController();
  if (key) {
    inflight.get(key)?.abort();
    inflight.set(key, ctl);
  }
  let res;
  try {
    res = await fetch(`${path}${qs.size ? '?' + qs : ''}`, { signal: ctl.signal });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError('Không kết nối được API');
  } finally {
    if (key && inflight.get(key) === ctl) inflight.delete(key);
  }
  if (!res.ok) throw new ApiError(`API trả lỗi ${res.status}`);
  return res.json();
}

export const isAbort = (e) => e?.name === 'AbortError';
