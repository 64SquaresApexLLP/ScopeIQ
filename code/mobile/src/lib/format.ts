export const money = (v: number | null | undefined) =>
  v == null ? '-' : `$${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
export const num = (v: number | null | undefined, d = 1) => (v == null ? '-' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d }));
export const when = (iso?: string | null) => (iso ? iso.replace('T', ' ').slice(0, 16) : '-');
export const label = (s?: string | null) => (s ? s.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : '-');
export const SECTOR: Record<string, string> = { A: 'Alpha', B: 'Beta', C: 'Gamma', D: 'Delta', SITE: 'Site' };
export const show = (v: unknown): string => {
  if (v == null || v === '') return '-';
  if (Array.isArray(v)) return v.map((x) => show(x)).join('\n');
  if (typeof v === 'object') {
    const o = v as Record<string, unknown>;
    if ('v' in o && Object.keys(o).length === 1) return show(o.v);
    return Object.entries(o).filter(([, x]) => x != null && x !== '').map(([k, x]) => `${k}: ${typeof x === 'object' ? JSON.stringify(x) : x}`).join(', ');
  }
  return String(v);
};
