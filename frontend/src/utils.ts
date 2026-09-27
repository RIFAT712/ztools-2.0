export const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : window.location.origin;

// GET without body, POST with JSON (or FormData) body. Throws with the server's `detail` on non-2xx.
export const api = async (path: string, body?: unknown) => {
  const init: RequestInit = { credentials: 'include' };
  if (body instanceof FormData) Object.assign(init, { method: 'POST', body });
  else if (body !== undefined) Object.assign(init, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const res = await fetch(API_BASE_URL + path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
};

export const toBengaliDigits = (num: number | string, useGrouping = true): string => {
  if (num === undefined || num === null) return '';
  const n = typeof num === 'string' ? parseFloat(num) : num;
  if (isNaN(n)) return num.toString();

  // Format with grouping if requested
  const formatted = useGrouping
    ? n.toLocaleString('en-IN')
    : n.toString();

  // Convert digits to Bengali
  const bengaliDigits = ['০', '১', '২', '৩', '৪', '৫', '৬', '৭', '৮', '৯'];
  return formatted.replace(/\d/g, (digit) => bengaliDigits[parseInt(digit)]);
};
