// ScopeIQ design tokens. One place for colour, type, spacing, radius and elevation; every screen reads from here.
// Palette: navy shell, blue for actions and active states, neutral surfaces for content.
import { Platform } from 'react-native';

export const colors = {
  // brand
  primary: '#142B4A',      // navy: sidebar, headings that need weight
  navy: '#142B4A',
  navy2: '#1B3760',        // navy hover / active row in the sidebar
  accent: '#2563EB',       // primary blue: actions, links, active states
  accentHover: '#1D4ED8',
  accent2: '#0F766E',      // teal (success family), used sparingly as a second accent
  soft: '#EEF4FF',         // tint behind active / selected items
  // surfaces
  bg: '#EFF4FA',
  card: '#FFFFFF',
  surface: '#FFFFFF',
  surfaceAlt: '#F7F9FC',   // table header, inset panels
  // text
  text: '#172B4D',
  muted: '#64748B',
  faint: '#94A3B8',
  // lines
  border: '#E2E8F0',
  borderStrong: '#CBD5E1',
  // status
  ok: '#0F766E',
  warn: '#D97706',
  danger: '#DC2626',
  info: '#2563EB',
  red: '#B91C1C',
  neutral: '#64748B',
};

/** Soft status tints (background, text) for badges and banners. */
export const tint = {
  ok: { bg: '#E6F4F2', fg: '#0F766E', line: '#B7DFD9' },
  warn: { bg: '#FEF3E2', fg: '#B45309', line: '#F8D9A8' },
  danger: { bg: '#FDECEC', fg: '#B91C1C', line: '#F6C4C4' },
  info: { bg: '#EAF1FE', fg: '#1D4ED8', line: '#C3D5FB' },
  neutral: { bg: '#F1F5F9', fg: '#475569', line: '#E2E8F0' },
};

export const font = {
  family: Platform.OS === 'web' ? 'Inter, "Segoe UI", system-ui, -apple-system, sans-serif' : undefined,
  mono: Platform.OS === 'web' ? '"JetBrains Mono", ui-monospace, Consolas, monospace' : 'monospace',
};

export const radius = { sm: 6, md: 8, lg: 10, xl: 12, pill: 999 };

// Flat elevation: a hairline plus a very soft drop. No glow, no coloured shadows.
export const shadow = { boxShadow: '0 1px 2px rgba(16,24,40,0.04)' } as const;
export const shadowLift = { boxShadow: '0 1px 2px rgba(16,24,40,0.05), 0 4px 12px rgba(16,24,40,0.06)' } as const;
export const shadowPopover = { boxShadow: '0 4px 6px rgba(16,24,40,0.05), 0 12px 32px rgba(16,24,40,0.12)' } as const;

// Gradients are retired from the design. Kept as a function so existing callers still work: it returns a flat colour.
export const gradient = (from: string, _to?: string, _deg?: number) => ({ backgroundColor: from } as any);
export const brandGradient = { backgroundColor: colors.navy } as any;

export const space = (n: number) => n * 4;

const STATUS: Record<string, string> = {
  OPEN: colors.danger, CONFIRMED: colors.warn, REDLINED: colors.info, RFI_RAISED: colors.info, BOM_ADJUSTED: colors.info,
  RESOLVED: colors.ok, CLOSED: colors.neutral, DISMISSED: colors.neutral, DRAFT: colors.warn, IN_REVIEW: colors.info, APPROVED: colors.ok,
  RECEIVED: colors.neutral, SP_REVIEW: colors.info, SP_AGREED: colors.ok, FBA: colors.ok, ANSWERED: colors.ok, SENT: colors.info,
  HIGH: colors.danger, MEDIUM: colors.warn, LOW: colors.info, CRITICAL: colors.red, ACK: colors.ok,
  SUCCEEDED: colors.ok, FAILED: colors.danger, SUCCEEDED_WITH_WARNINGS: colors.warn, RUNNING: colors.info,
  DONE: colors.ok, PENDING: colors.neutral, SKIPPED: colors.neutral,
  NEW: colors.ok, REMOVED: colors.danger, EXISTING: colors.neutral, RELOCATED: colors.warn, REUSED: colors.info,
  Install: colors.ok, Remove: colors.danger, DUPLICATE: colors.warn, INCORPORATED: colors.ok,
};
export const statusColor = (s?: string | null) => (s && STATUS[s]) || colors.accent;

/** Background/text pair for a status colour (falls back to a generic tint of the colour). */
export function tintFor(color: string) {
  const hit = Object.values(tint).find((t) => t.fg.toLowerCase() === color.toLowerCase());
  if (hit) return hit;
  if (color === colors.ok) return tint.ok;
  if (color === colors.warn) return tint.warn;
  if (color === colors.danger || color === colors.red) return tint.danger;
  if (color === colors.info || color === colors.accent) return tint.info;
  if (color === colors.neutral || color === colors.muted) return tint.neutral;
  return { bg: color + '14', fg: color, line: color + '33' };
}
