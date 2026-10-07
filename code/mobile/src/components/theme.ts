export const colors = {
  bg: '#F4F6FA', card: '#FFFFFF', text: '#1B2433', muted: '#5E6B7E', border: '#DCE2EA', primary: '#1F3864', accent: '#2F6FED',
  danger: '#C62828', warn: '#B26A00', ok: '#2E7D32', info: '#1565C0', red: '#D50000',
};
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
