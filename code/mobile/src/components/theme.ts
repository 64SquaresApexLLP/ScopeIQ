export const colors = {
  bg: '#F4F6FB', card: '#FFFFFF', text: '#0F172A', muted: '#64748B', border: '#E3E8F2', primary: '#0F2A5F', accent: '#4F6BFF',
  accent2: '#14B8A6', soft: '#EEF2FF', danger: '#DC2626', warn: '#D97706', ok: '#16A34A', info: '#2563EB', red: '#B91C1C',
  surface: '#FFFFFF', surfaceAlt: '#F4F6FB',
};
// soft layered shadow (works on web and native)
export const shadow = { boxShadow: '0 1px 2px rgba(15,23,42,0.05), 0 6px 20px rgba(15,23,42,0.06)' } as const;
export const shadowLift = { boxShadow: '0 2px 4px rgba(15,23,42,0.06), 0 12px 28px rgba(79,107,255,0.16)' } as const;
// linear gradient background; the solid colour is the fallback where gradients are unsupported
export const gradient = (from: string, to: string, deg = 135) =>
  ({ backgroundColor: from, experimental_backgroundImage: `linear-gradient(${deg}deg, ${from}, ${to})`, backgroundImage: `linear-gradient(${deg}deg, ${from}, ${to})` } as any);
export const brandGradient = gradient('#0F2A5F', '#4F46E5');
export const space = (n: number) => n * 4;

const STATUS: Record<string, string> = {
  OPEN: colors.danger, CONFIRMED: colors.warn, REDLINED: colors.info, RFI_RAISED: colors.info, BOM_ADJUSTED: colors.info,
  RESOLVED: colors.ok, CLOSED: colors.muted, DISMISSED: colors.muted, DRAFT: colors.warn, IN_REVIEW: colors.info, APPROVED: colors.ok,
  RECEIVED: colors.muted, SP_REVIEW: colors.info, SP_AGREED: colors.ok, FBA: colors.ok, ANSWERED: colors.ok, SENT: colors.info,
  HIGH: colors.danger, MEDIUM: colors.warn, LOW: colors.info, CRITICAL: colors.red, ACK: colors.ok,
  SUCCEEDED: colors.ok, FAILED: colors.danger, SUCCEEDED_WITH_WARNINGS: colors.warn, RUNNING: colors.info,
  NEW: colors.ok, REMOVED: colors.danger, EXISTING: colors.muted, RELOCATED: colors.warn, REUSED: colors.info,
  Install: colors.ok, Remove: colors.danger,
};
export const statusColor = (s?: string | null) => (s && STATUS[s]) || colors.accent;
