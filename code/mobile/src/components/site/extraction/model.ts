// Extraction model for stage 2 (CD + drone) and stage 5 (RFDS + MA/SA). Everything is derived from
// /pipeline/runs/{run}/steps/EXTRACT and /steps/DESIGN; nothing is invented. Field status rules:
//   Verified      a person reviewed the value (REVIEWED_BY set)          - never inferred from presence
//   Needs review  the backend flagged it (NEEDS_REVIEW, or no catalog match for an RFDS item)
//   Extracted     read by the pipeline, not reviewed and not flagged
//   Missing / Extraction failed apply to a whole document (required file absent, or the reader reported a problem)
import { show } from '../../../lib/format';
import { Row } from '../../../lib/types';
import { colors } from '../../theme';

type IconName = import('../../ui').IconName;

export type FieldStatus = 'VERIFIED' | 'REVIEW' | 'EXTRACTED' | 'MISSING' | 'FAILED';
export const FIELD_STATUS: Record<FieldStatus, { label: string; color: string; bg: string; line: string; icon: IconName }> = {
  VERIFIED: { label: 'Verified', color: '#0F766E', bg: '#ECF7F5', line: '#B7DFD9', icon: 'check-circle' },
  REVIEW: { label: 'Needs review', color: '#B45309', bg: '#FEF6E7', line: '#F8D9A8', icon: 'alert-triangle' },
  EXTRACTED: { label: 'Extracted', color: '#2563EB', bg: '#EEF4FF', line: '#C3D5FB', icon: 'cpu' },
  MISSING: { label: 'Missing', color: '#64748B', bg: '#F1F5F9', line: '#CBD5E1', icon: 'slash' },
  FAILED: { label: 'Extraction failed', color: '#DC2626', bg: '#FDEEEE', line: '#F6C4C4', icon: 'x-circle' },
};

/** One value shown in the workspace, whatever table it came from. */
export interface XField {
  id: string;
  category: string;
  label: string;            // e.g. "Alpha 1 · Radio"
  value: string;            // what was read
  detail?: string;          // supporting facts (height, azimuth, P/N ...)
  status: FieldStatus;
  confidence?: number | null;
  docId?: string | null;    // source document, when known
  where?: string | null;    // sheet / page / drone object id, used to open the source at that place
  whereLabel?: string | null;
  method?: string | null;
}

export interface XDocument { docId?: string | null; name: string; format?: string; revision?: string; status?: string; type: string }

export interface XCard {
  key: 'CD' | 'DRONE' | 'RFDS' | 'MA_SA';
  title: string;
  icon: IconName;
  documents: XDocument[];   // files of this source (current first)
  primary?: XDocument;      // the file the values were read from
  status: FieldStatus;
  statusNote?: string;
  method?: string;
  fields: XField[];
  summary: string[];        // compact facts
  issues: string[];
}

const SECTOR: Record<string, string> = { A: 'Alpha', B: 'Beta', C: 'Gamma', D: 'Delta' };
const KIND: Record<string, string> = { radio: 'Radio', passive: 'Passive antenna', air: 'Active antenna (AAU)', pipe: 'Mount pipe', sled: 'Sled / frame', trunk: 'Trunk cable', baseband: 'Baseband' };
const kindLabel = (k?: string) => (k ? KIND[k] ?? k.replace(/_/g, ' ') : '');
const where = (sector?: string | null, pos?: number | string | null) =>
  sector ? `${SECTOR[sector] ?? sector}${pos != null && pos !== '' ? ` ${pos}` : ''}` : 'Site';
const num = (v: unknown, unit = '') => (v == null || v === '' ? null : `${Math.round(Number(v) * 10) / 10}${unit}`);
const plain = (v: unknown): string => {
  if (v && typeof v === 'object' && !Array.isArray(v) && 'v' in (v as any) && Object.keys(v as any).length === 1) return plain((v as any).v);
  return show(v);
};

function categoryFor(kind: string, source: 'CD' | 'FIELD'): string {
  if (kind === 'passive' || kind === 'air') return 'Antenna details';
  if (kind === 'radio') return 'Equipment details';
  if (kind === 'pipe' || kind === 'sled') return 'Tower structure and mounts';
  if (kind === 'trunk') return 'Measurements';
  return source === 'FIELD' ? 'Drone observations' : 'Equipment details';
}

/** "CD:A1:radio" -> {source CD, sector A, position 1, kind radio}; "CD:trunk" -> kind trunk. */
function parseName(name: string) {
  const [source, loc, kind] = name.split(':');
  if (!kind) return { source, sector: null as string | null, position: null as string | null, kind: loc };
  const m = /^([A-Z])(\d*)$/.exec(loc ?? '');
  return { source, sector: m ? m[1] : loc, position: m && m[2] ? m[2] : null, kind };
}

function fieldStatus(f: Row): FieldStatus {
  if (f.REVIEWED_BY) return 'VERIFIED';
  if (f.NEEDS_REVIEW) return 'REVIEW';
  return 'EXTRACTED';
}

const docOf = (d: Row): XDocument => ({ docId: d.DOC_ID, name: d.FILE_NAME, format: d.FILE_FORMAT, revision: d.REVISION, status: d.STATUS, type: d.DOC_TYPE });
const currentFirst = (a: XDocument, b: XDocument) => (a.status === 'CURRENT' ? 0 : 1) - (b.status === 'CURRENT' ? 0 : 1);

/** Stage 2: Construction drawing and drone survey only. */
export function stage2Cards(x: any, stepStatus: string): XCard[] {
  const cd = x?.cd_extraction ?? {}, dr = x?.drone_extraction ?? {};
  const fields: Row[] = x?.fields ?? [];
  const lines: Row[] = x?.config_lines ?? [];

  const toField = (f: Row): XField => {
    const p = parseName(String(f.FIELD_NAME ?? ''));
    return {
      id: f.FIELD_ID, category: categoryFor(p.kind, p.source === 'FIELD' ? 'FIELD' : 'CD'),
      label: p.kind === 'trunk' ? 'Trunk cable schedule' : `${where(p.sector, p.position)} · ${kindLabel(p.kind)}`,
      value: plain(f.VALUE), status: fieldStatus(f), confidence: f.CONFIDENCE != null ? Number(f.CONFIDENCE) : null,
      docId: f.DOC_ID, where: f.PAGE ?? null, whereLabel: f.PAGE ? (String(f.PAGE).startsWith('PC-') ? `Object ${f.PAGE}` : `Sheet ${f.PAGE}`) : null, method: f.METHOD,
    };
  };
  // measurements read alongside each item (rad center, azimuth, tilt) from the configuration lines of the same run
  const measure = (src: 'CD' | 'FIELD', docId?: string | null): XField[] =>
    lines.filter((l) => l.SOURCE === src && (l.RAD_CENTER_FT != null || l.AZIMUTH_DEG != null || l.MECH_TILT != null)).map((l) => ({
      id: l.LINE_ID, category: 'Measurements', label: `${where(l.SECTOR, l.POSITION)} · ${kindLabel(l.KIND)}`,
      value: [num(l.RAD_CENTER_FT, ' ft rad center'), num(l.AZIMUTH_DEG, '° azimuth'), num(l.MECH_TILT, '° tilt')].filter(Boolean).join('  ·  '),
      detail: l.SOURCE_REF ?? undefined, status: 'EXTRACTED' as FieldStatus, confidence: l.CONFIDENCE != null ? Number(l.CONFIDENCE) : null,
      docId: src === 'CD' ? docId : null, where: src === 'CD' ? (/\bA-\d+\b/.exec(String(l.SOURCE_REF ?? ''))?.[0] ?? null) : null,
      whereLabel: src === 'CD' ? (/\bA-\d+\b/.exec(String(l.SOURCE_REF ?? ''))?.[0] ? `Sheet ${/\bA-\d+\b/.exec(String(l.SOURCE_REF))![0]}` : null) : null,
    }));

  const cdDocs: XDocument[] = (cd.documents ?? []).map(docOf).sort(currentFirst);
  const cdFields = fields.filter((f) => String(f.FIELD_NAME ?? '').startsWith('CD:')).map(toField);
  const cdPrimaryId = cdFields.find((f) => f.docId)?.docId;
  const cdPrimary = cdDocs.find((d) => d.docId === cdPrimaryId) ?? cdDocs[0];
  const cdIssues: string[] = cd.issues ?? [];
  const cdAll = [...cdFields, ...measure('CD', cdPrimary?.docId)];
  const cdStatus: FieldStatus = !cdDocs.length ? 'MISSING' : cdIssues.length && !cdFields.length ? 'FAILED' : stepStatus === 'FAILED' && !cdFields.length ? 'FAILED'
    : cdAll.some((f) => f.status === 'REVIEW') ? 'REVIEW' : cdAll.length && cdAll.every((f) => f.status === 'VERIFIED') ? 'VERIFIED' : 'EXTRACTED';

  const drDocs: XDocument[] = (dr.documents ?? []).map(docOf).sort(currentFirst);
  const drFields = fields.filter((f) => String(f.FIELD_NAME ?? '').startsWith('FIELD:')).map(toField);
  const drPrimaryId = drFields.find((f) => f.docId)?.docId;
  const drPrimary = drDocs.find((d) => d.docId === drPrimaryId) ?? drDocs.find((d) => /POINTCLOUD|VENDOR/.test(d.type)) ?? drDocs[0];
  const objects: XField[] = (dr.identified_objects ?? []).map((o: any) => ({
    id: `obj-${o.object_id}`, category: 'Drone observations', label: `${o.object_id} · ${o.object_type}${o.sector ? ` · ${where(o.sector, o.position)}` : ''}`,
    value: o.catalog?.model ?? o.model_guess ?? o.object_type,
    detail: [num(o.center_height_ft, ' ft high'), num(o.facing_az_deg, '° facing'), Array.isArray(o.dims_in) ? `${o.dims_in.map((d: number) => Math.round(d)).join(' × ')} in` : null,
      o.catalog?.basis ? `match: ${o.catalog.basis}` : null].filter(Boolean).join('  ·  '),
    status: 'EXTRACTED' as FieldStatus, confidence: o.confidence != null ? Number(o.confidence) : null,
    docId: drPrimary?.docId, where: o.object_id, whereLabel: `Object ${o.object_id}`, method: o.method ?? dr.method,
  }));
  const drAll = [...drFields, ...measure('FIELD'), ...objects];
  const drStatus: FieldStatus = !drDocs.length ? 'MISSING' : stepStatus === 'FAILED' && !drFields.length ? 'FAILED'
    : drAll.some((f) => f.status === 'REVIEW') ? 'REVIEW' : drAll.length && drAll.every((f) => f.status === 'VERIFIED') ? 'VERIFIED' : 'EXTRACTED';

  const reviewOf = (a: XField[]) => a.filter((f) => f.status === 'REVIEW').length;
  return [
    {
      key: 'CD', title: 'Construction drawing', icon: 'file-text', documents: cdDocs, primary: cdPrimary, status: cdStatus, method: cd.method,
      statusNote: cdStatus === 'MISSING' ? 'No construction drawing was registered.' : cdStatus === 'FAILED' ? 'The drawing could not be read.' : undefined,
      fields: cdAll, issues: cdIssues,
      summary: [`${cdFields.length} values read`, `${cd.items_count ?? 0} drawing items`, reviewOf(cdAll) ? `${reviewOf(cdAll)} need review` : 'nothing flagged', cd.revision ? `revision ${cd.revision}` : ''].filter(Boolean),
    },
    {
      key: 'DRONE', title: 'Drone survey', icon: 'camera', documents: drDocs, primary: drPrimary, status: drStatus, method: dr.method,
      statusNote: drStatus === 'MISSING' ? 'No drone survey files were registered.' : drStatus === 'FAILED' ? 'The drone survey could not be read.' : undefined,
      fields: drAll, issues: [],
      summary: [`${drFields.length} values read`, `${dr.objects_count ?? objects.length} objects identified`, reviewOf(drAll) ? `${reviewOf(drAll)} need review` : 'nothing flagged', `${drDocs.length} files`].filter(Boolean),
    },
  ];
}

/** Stage 5: RFDS and MA/SA only. `docIndex` maps file names to document ids (from the run's registered documents). */
export function stage5Cards(x: any, docIndex: Record<string, Row>): XCard[] {
  const docs: any[] = x?.documents ?? [];
  const items: Row[] = x?.items ?? [];
  const card = (key: 'RFDS' | 'MA_SA'): XCard => {
    const d = docs.find((y) => y.doc_type === key);
    const reg = d ? docIndex[d.file_name] : undefined;
    const doc: XDocument | undefined = d ? { docId: reg?.DOC_ID ?? null, name: d.file_name, format: d.format, revision: d.revision, status: d.status, type: key } : undefined;
    const mine = items.filter((i) => (key === 'RFDS' ? !/MA|SA/i.test(String(i.SOURCE ?? '')) : /MA|SA/i.test(String(i.SOURCE ?? ''))));
    const fields: XField[] = mine.map((i) => {
      const cat = i.KIND === 'baseband' ? 'Configuration details' : i.KIND === 'mount' || /mount/i.test(String(i.CATEGORY ?? '')) ? 'Mount information'
        : i.ACTION && i.ACTION !== 'Existing' ? 'Equipment changes' : 'Radio and antenna details';
      const page = /^p(\d+)$/i.exec(String(i.DRAWING ?? ''))?.[1] ?? null;
      return {
        id: i.ITEM_ID, category: cat, label: `${where(i.SECTOR, i.POSITION)} · ${kindLabel(i.KIND)}`,
        value: [i.MODEL, i.ACTION ? `(${i.ACTION})` : ''].filter(Boolean).join(' '),
        detail: [i.QTY != null ? `qty ${num(i.QTY)}` : null, num(i.RAD_CENTER_FT, ' ft rad center'), i.TECHNOLOGY, i.BAND, i.MANUFACTURER_PN ? `P/N ${i.MANUFACTURER_PN}` : null,
          i.MATCH_STATUS && i.MATCH_STATUS !== 'Matched' ? `catalog: ${i.MATCH_STATUS}` : null].filter(Boolean).join('  ·  '),
        status: (i.MATCH_STATUS && i.MATCH_STATUS !== 'Matched' ? 'REVIEW' : 'EXTRACTED') as FieldStatus,
        confidence: i.CONFIDENCE != null ? Number(i.CONFIDENCE) : null,
        docId: i.SOURCE_DOC_ID ?? doc?.docId, where: page, whereLabel: page ? `Page ${page}` : null, method: d?.tool,
      };
    });
    const status: FieldStatus = !d ? 'MISSING' : fields.some((f) => f.status === 'REVIEW') ? 'REVIEW' : 'EXTRACTED';
    const summary = key === 'RFDS'
      ? [`${d?.values ?? 0} values read`, `${fields.length} equipment items`, fields.some((f) => f.status === 'REVIEW') ? `${fields.filter((f) => f.status === 'REVIEW').length} not matched to the catalog` : 'all matched to the catalog']
      : [`${d?.values ?? 0} values read`, d?.result ? `analysis result: ${d.result}` : '', `${x?.items?.filter((i: Row) => /mount/i.test(String(i.CATEGORY ?? ''))).length ?? 0} mount changes`].filter(Boolean);
    return {
      key, title: key === 'RFDS' ? 'RFDS report' : 'MA/SA report', icon: key === 'RFDS' ? 'radio' : 'shield', documents: doc ? [doc] : [], primary: doc, status, method: d?.tool,
      statusNote: !d ? (key === 'RFDS' ? 'No RFDS was read.' : 'No MA/SA report was read. Mount reinforcement is not evaluated without it.') : undefined,
      fields, issues: [], summary,
    };
  };
  return [card('RFDS'), card('MA_SA')];
}

export const CATEGORY_ORDER = ['Site information', 'Tower structure and mounts', 'Antenna details', 'Equipment details', 'Measurements', 'Drone observations',
  'Equipment changes', 'Radio and antenna details', 'Mount information', 'Structural analysis', 'Configuration details'];
export const CATEGORY_ICON: Record<string, IconName> = {
  'Site information': 'map-pin', 'Tower structure and mounts': 'triangle', 'Antenna details': 'radio', 'Equipment details': 'cpu', Measurements: 'maximize-2',
  'Drone observations': 'camera', 'Equipment changes': 'repeat', 'Radio and antenna details': 'radio', 'Mount information': 'anchor', 'Structural analysis': 'shield', 'Configuration details': 'sliders',
};
export const neutral = colors.neutral;
