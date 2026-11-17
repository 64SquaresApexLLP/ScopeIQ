// Pipeline run model: the six stages, how each one looks (derived only from the run the API returned), and what the
// inspector shows as inputs, outputs, logs and actions. Nothing here invents data: every number comes from the run's
// STEPS (status, counts, message, timing) or from /pipeline/runs/{run}/steps/{key}.
import { duration } from '../StageTimeline';
import { PipelineRun, PipelineStep } from '../../../lib/types';
import { colors } from '../../theme';

type IconName = import('../../ui').IconName;

export const STAGES: { key: string; title: string; description: string; icon: IconName }[] = [
  { key: 'INGEST', title: 'Ingest documents', description: 'Registers the site files and their revisions.', icon: 'inbox' },
  { key: 'EXTRACT', title: 'Extract values', description: 'Reads the construction drawing and the drone survey.', icon: 'cpu' },
  { key: 'RECONCILE', title: 'Reconcile sources', description: 'Compares the construction drawing (CD) with the drone survey.', icon: 'git-merge' },
  { key: 'REDLINES', title: 'Redlines & RFIs', description: 'Turns each mismatch into a drawing redline or an RFI.', icon: 'edit-3' },
  { key: 'DESIGN', title: 'Extract RFDS & MA/SA', description: 'Reads equipment changes from the RFDS and the mount analysis.', icon: 'radio' },
  { key: 'BOM', title: 'Generate BOM', description: 'Builds the bill of materials from the BOM rules and material catalog.', icon: 'list' },
];
export const stageMeta = (key: string, i: number) => STAGES.find((s) => s.key === key) ?? { key, title: key, description: '', icon: 'circle' as IconName, i };

export type StageState = 'COMPLETED' | 'RUNNING' | 'REVIEW' | 'FAILED' | 'PENDING' | 'SKIPPED' | 'BLOCKED';

export const STATE: Record<StageState, { label: string; color: string; bg: string; line: string; icon: IconName }> = {
  COMPLETED: { label: 'Completed', color: '#0F766E', bg: '#ECF7F5', line: '#B7DFD9', icon: 'check' },
  RUNNING: { label: 'Running', color: '#2563EB', bg: '#EEF4FF', line: '#BFD3FB', icon: 'loader' },
  REVIEW: { label: 'Review required', color: '#D97706', bg: '#FEF6E7', line: '#F8D9A8', icon: 'alert-triangle' },
  FAILED: { label: 'Failed', color: '#DC2626', bg: '#FDEEEE', line: '#F6C4C4', icon: 'x' },
  PENDING: { label: 'Pending', color: '#94A3B8', bg: '#F8FAFC', line: '#E2E8F0', icon: 'clock' },
  SKIPPED: { label: 'Skipped', color: '#64748B', bg: '#F8FAFC', line: '#CBD5E1', icon: 'skip-forward' },
  BLOCKED: { label: 'Not run', color: '#94A3B8', bg: '#F8FAFC', line: '#E2E8F0', icon: 'lock' },
};

const n = (v: unknown) => (typeof v === 'number' ? v : Number(v) || 0);

/** A completed stage that left something for a person to look at. */
export function needsReview(st: PipelineStep): boolean {
  const c = st.counts ?? {};
  if (st.key === 'EXTRACT') return n(c.needs_review) > 0;
  if (st.key === 'RECONCILE') return n(c.rules) > 0;
  if (st.key === 'REDLINES') return n(c.redlines) + n(c.rfis) > 0;
  if (st.key === 'BOM') return n(c.issues) + n(c.needs_review) > 0;
  return false;
}

export function stageState(steps: PipelineStep[], i: number): StageState {
  const st = steps[i];
  if (st.status === 'RUNNING') return 'RUNNING';
  if (st.status === 'FAILED') return 'FAILED';
  if (st.status === 'SKIPPED') return 'SKIPPED';
  if (st.status === 'DONE') return needsReview(st) ? 'REVIEW' : 'COMPLETED';
  const failedAt = steps.findIndex((x) => x.status === 'FAILED');
  return failedAt >= 0 && i > failedAt ? 'BLOCKED' : 'PENDING';
}

export type RunState = 'NOT_STARTED' | 'RUNNING' | 'COMPLETED' | 'FINDINGS' | 'FAILED' | 'STOPPED';
export const RUN_STATE: Record<RunState, { label: string; color: string }> = {
  NOT_STARTED: { label: 'Not started', color: colors.neutral }, RUNNING: { label: 'Running', color: '#2563EB' },
  COMPLETED: { label: 'Completed', color: '#0F766E' }, FINDINGS: { label: 'Completed with findings', color: '#D97706' },
  FAILED: { label: 'Failed', color: '#DC2626' }, STOPPED: { label: 'Stopped after stage 4', color: '#D97706' },
};

export function runState(run: PipelineRun | null | undefined, steps: PipelineStep[] | null): RunState {
  if (!run) return 'NOT_STARTED';
  if (run.STATUS === 'RUNNING') return 'RUNNING';
  if (run.STATUS === 'FAILED' || steps?.some((s) => s.status === 'FAILED')) return 'FAILED';
  if (steps?.some((s) => s.status === 'SKIPPED')) return 'STOPPED';
  if (steps?.some(needsReview) || run.STATUS === 'SUCCEEDED_WITH_WARNINGS') return 'FINDINGS';
  return 'COMPLETED';
}

export const elapsed = (a?: string | null, b?: string | null) => {
  if (!a) return '';
  const end = b ? new Date(b).getTime() : Date.now();
  return duration(Math.max(0, end - new Date(a).getTime()));
};

/** One-line result shown on a stage card, from the step's own counts and message. */
export function stageSummary(st: PipelineStep): string {
  const c = st.counts ?? {};
  switch (st.key) {
    case 'INGEST': {
      if (st.status !== 'DONE') return st.message;
      const total = Object.entries(c).reduce((a, [, v]) => a + n(v), 0);
      return `${total} document${total === 1 ? '' : 's'} registered across ${Object.keys(c).length} type${Object.keys(c).length === 1 ? '' : 's'}`;
    }
    case 'EXTRACT':
      return st.status === 'DONE' ? `${n(c.values)} values read  ·  ${n(c.comparison_records)} comparison records${n(c.needs_review) ? `  ·  ${c.needs_review} need review` : ''}` : st.message;
    case 'RECONCILE':
      return st.status === 'DONE' ? `${n(c.comparisons)} comparisons  ·  ${n(c.rules)} mismatch${n(c.rules) === 1 ? '' : 'es'}` : st.message;
    case 'REDLINES':
      return st.status === 'DONE' ? `${n(c.redlines)} redline${n(c.redlines) === 1 ? '' : 's'}  ·  ${n(c.rfis)} RFI${n(c.rfis) === 1 ? '' : 's'}` : st.message;
    case 'DESIGN':
      return st.status === 'DONE' ? `${n(c.items)} equipment items  ·  ${n(c.mount_changes)} mount changes from ${n(c.documents)} documents` : st.message;
    case 'BOM':
      return st.status === 'DONE' ? `${n(c.lines)} BOM lines  ·  ${n(c.issues)} issue${n(c.issues) === 1 ? '' : 's'}` : st.message;
    default:
      return st.message;
  }
}

/** Required documents for stage 1, checked against the document types the step registered. */
export const REQUIRED_DOCS: { label: string; anyOf: string[] }[] = [
  { label: 'Construction drawing (CD)', anyOf: ['CD'] },
  { label: 'Drone orbit video', anyOf: ['DRONE_VIDEO'] },
  { label: 'Drone vendor CSV or point cloud', anyOf: ['DRONE_VENDOR', 'DRONE_POINTCLOUD'] },
];

export interface IoItem { label: string; detail?: string; status?: string; statusColor?: string; icon?: IconName; href?: string }
export interface Inspection { inputs: IoItem[]; outputs: IoItem[]; notes: string[] }

const fileIcon = (name = ''): IconName => (/\.(mp4|mov|avi)$/i.test(name) ? 'video' : /\.(jpe?g|png|tif)$/i.test(name) ? 'image' : /\.(xlsx|csv)$/i.test(name) ? 'grid' : /\.la[sz]$/i.test(name) ? 'box' : 'file-text');
const docStatus = (s?: string) => (s === 'SUPERSEDED' ? { status: 'Superseded', statusColor: colors.neutral } : s ? { status: 'Current', statusColor: colors.ok } : {});

/** Inputs, outputs and notes for the inspector, from the stage detail the API returned (null until loaded). */
export function inspect(key: string, x: any, step: PipelineStep): Inspection {
  const out: Inspection = { inputs: [], outputs: [], notes: [] };
  if (!x) return out;
  const c = step.counts ?? {};
  switch (key) {
    case 'INGEST': {
      for (const d of (x.documents ?? []).slice(0, 40)) out.inputs.push({ label: d.FILE_NAME, detail: [d.DOC_TYPE?.replace(/_/g, ' '), d.REVISION].filter(Boolean).join('  ·  '), icon: fileIcon(d.FILE_NAME), ...docStatus(d.STATUS) });
      out.outputs.push({ label: 'Documents registered', detail: String(x.total ?? 0) });
      out.outputs.push({ label: 'Current revisions', detail: String(x.current_count ?? 0) });
      if (x.superseded_count) out.outputs.push({ label: 'Superseded revisions', detail: String(x.superseded_count) });
      if (x.formats?.length) out.outputs.push({ label: 'File formats', detail: x.formats.join(', ') });
      break;
    }
    case 'EXTRACT': {
      const cd = x.cd_extraction ?? {}, dr = x.drone_extraction ?? {};
      for (const d of cd.documents ?? []) out.inputs.push({ label: d.FILE_NAME, detail: `Drawing  ·  ${cd.method ?? ''}`.trim(), icon: fileIcon(d.FILE_NAME), ...docStatus(d.STATUS) });
      for (const d of dr.documents ?? []) out.inputs.push({ label: d.FILE_NAME, detail: `Drone  ·  ${d.DOC_TYPE?.replace(/_/g, ' ') ?? ''}`, icon: fileIcon(d.FILE_NAME), ...docStatus(d.STATUS) });
      out.outputs.push({ label: 'Values read', detail: String(x.total ?? c.values ?? 0) });
      out.outputs.push({ label: 'Comparison records', detail: String(x.comparison_summary?.total ?? c.comparison_records ?? 0) });
      if (cd.items_count != null) out.outputs.push({ label: 'Drawing items', detail: `${cd.items_count} (read by ${c.cd_read_by ?? cd.method ?? '-'})` });
      if (dr.objects_count != null) out.outputs.push({ label: 'Drone objects', detail: `${dr.objects_count} (read by ${c.field_read_by ?? dr.method ?? '-'})` });
      if (x.needs_review) out.outputs.push({ label: 'Values needing review', detail: String(x.needs_review), status: 'Review', statusColor: colors.warn });
      for (const i of cd.issues ?? []) out.notes.push(`Drawing: ${i}`);
      break;
    }
    case 'RECONCILE': {
      const cmp: any[] = x.comparisons ?? [];
      const files = new Set<string>();
      for (const k of cmp) for (const side of [k.left, k.right]) for (const f of side?.files ?? []) files.add(`${side.label}|${f}`);
      for (const f of files) { const [lbl, name] = f.split('|'); out.inputs.push({ label: name, detail: lbl, icon: fileIcon(name) }); }
      for (const k of cmp) out.outputs.push({ label: k.title, detail: `${k.compared ?? 0} compared  ·  ${k.mismatched ?? 0} mismatched`, status: k.status === 'MATCH' ? 'Match' : k.status === 'MISMATCH' ? 'Mismatch' : String(k.status ?? '').toLowerCase(), statusColor: k.status === 'MATCH' ? colors.ok : k.status === 'MISMATCH' ? colors.danger : colors.neutral });
      const matches = cmp.filter((k) => k.status === 'MATCH').length;
      out.notes.push(`${matches} of ${cmp.length} checks match; ${(x.discrepancies ?? []).length} discrepanc${(x.discrepancies ?? []).length === 1 ? 'y' : 'ies'} logged.`);
      for (const d of x.discrepancies ?? []) out.notes.push(`${d.RULE_ID ?? ''} ${d.TITLE ?? ''}`.trim());
      break;
    }
    case 'REDLINES': {
      const dec = x.decision ?? {};
      for (const it of dec.items ?? []) out.inputs.push({ label: it.title ?? it.disc_id, detail: it.rule_id, icon: 'alert-triangle' });
      const reds: any[] = x.redlines ?? [], rfis: any[] = x.rfis ?? [];
      const openRfi = rfis.filter((r) => !['ANSWERED', 'CLOSED'].includes(r.STATUS)).length;
      out.outputs.push({ label: 'Redlines generated', detail: String(reds.length) });
      out.outputs.push({ label: 'RFIs', detail: `${rfis.length} (${openRfi} open, ${rfis.length - openRfi} resolved)` });
      if (x.files?.redlined_cd_pdf) out.outputs.push({ label: 'Redlined drawing (PDF)', detail: x.files.redlined_cd_pdf.split('/').pop(), icon: 'file-text', href: `/files/${x.files.redlined_cd_pdf}`, status: 'Available', statusColor: colors.ok });
      const evid = reds.some((r) => r.PDF_PATH);
      out.outputs.push({ label: 'Evidence', detail: reds.length ? (evid ? 'Drone proof attached to the redlined drawing' : 'No drawing written') : 'Not needed', status: reds.length ? (evid ? 'Available' : 'Missing') : undefined, statusColor: evid ? colors.ok : colors.warn });
      if (dec.reason) out.notes.push(dec.reason);
      break;
    }
    case 'DESIGN': {
      for (const d of x.documents ?? []) out.inputs.push({ label: d.file_name, detail: [d.doc_type?.replace(/_/g, ' '), d.revision, d.tool].filter(Boolean).join('  ·  '), icon: fileIcon(d.file_name), status: d.result ?? (d.status === 'CURRENT' ? 'Read' : d.status), statusColor: colors.ok });
      out.outputs.push({ label: 'Equipment items', detail: String(x.total ?? 0) });
      if (c.mount_changes != null) out.outputs.push({ label: 'Mount changes', detail: String(c.mount_changes) });
      if (x.skipped && x.reason) out.notes.push(x.reason);
      break;
    }
    case 'BOM': {
      const rb = x.rulebook ?? null;
      if (rb?.files) {
        out.inputs.push({ label: rb.files.rules, detail: `BOM rules  ·  ${rb.rules ?? 0} rules`, icon: 'grid' });
        out.inputs.push({ label: rb.files.catalog, detail: `Material catalog  ·  ${rb.catalog_items ?? 0} items`, icon: 'grid' });
      }
      out.outputs.push({ label: 'BOM lines', detail: String(x.total ?? 0) });
      if (rb) out.outputs.push({ label: 'Rules applied', detail: String(rb.applied ?? 0), status: 'Applied', statusColor: colors.ok });
      if (rb) out.outputs.push({ label: 'Rules not applied', detail: String((rb.not_applied ?? []).length), status: (rb.not_applied ?? []).length ? 'Check' : undefined, statusColor: colors.danger });
      if (x.file) out.outputs.push({ label: 'BOM workbook', detail: String(x.file).split('/').pop(), icon: 'download', href: `/files/${x.file}`, status: 'Ready to export', statusColor: colors.ok });
      if (x.trunk?.key) out.notes.push(`Trunk: ${x.trunk.key} (${x.trunk.length_ft ?? '-'} ft required ${x.trunk.required_ft ?? '-'} ft)`);
      for (const r of rb?.not_applied ?? []) out.notes.push(`${r.rule_id ?? r.id ?? ''} not applied: ${r.problem ?? r.reason ?? ''}`.trim());
      for (const i of x.issues ?? []) out.notes.push(`${i.severity ?? ''} ${i.message ?? ''}`.trim());
      if (x.skipped && x.reason) out.notes.push(x.reason);
      break;
    }
  }
  return out;
}

/** Warnings of the run that belong to a stage (the backend prefixes them with the source). */
export function stageWarnings(run: PipelineRun | null, key: string): string[] {
  const w = (run?.WARNINGS ?? []).map(String);
  if (key === 'EXTRACT') return w.filter((x) => /^(cd|video|drone|field|pointcloud|vendor):/i.test(x));
  if (key === 'INGEST') return w.filter((x) => /required documents|no documents/i.test(x));
  return [];
}
