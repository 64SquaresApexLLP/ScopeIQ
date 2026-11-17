// Site Overview tab: site header + information grid, the document revision check (the backend's result, shown as is) and
// a grouped document register with status filters, collapsible groups, preview and download.
import { router } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Linking, Pressable, Text, View, useWindowDimensions } from 'react-native';
import { FilePreviewModal, FilePreviewTarget } from '../FilePreviewModal';
import { api, ApiError, authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { Row as R, SiteDetail } from '../../lib/types';
import { mutateApi } from '../../lib/useApi';
import { colors, radius, shadow, space } from '../theme';
import { Badge, Button, Card, Chips, ConfirmDialog, EmptyState, ErrorView, humanize, Icon, IconName } from '../ui';

const web = (style: object) => style as any;

// ------------------------------------------------------------------ formatting
const size = (n?: number | null) =>
  !n ? null : n >= 1073741824 ? `${(n / 1073741824).toFixed(1)} GB` : n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;

const parseDate = (v?: string | null) => {
  if (!v) return null;
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(v) ? `${v}T00:00:00` : v);
  return isNaN(d.getTime()) ? null : d;
};
const fmtDate = (v?: string | null) => parseDate(v)?.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) ?? null;
const fmtDateTime = (v?: string | null) => {
  const d = parseDate(v);
  return d ? `${fmtDate(v)}, ${d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}` : null;
};

// ------------------------------------------------------------------ document types and statuses
const TYPE_ORDER = ['CD', 'DRONE_POINTCLOUD', 'DRONE_VIDEO', 'MA_SA', 'RFDS', 'BOM_REV0', 'DRONE_VENDOR', 'DRONE_META', 'DRONE_IMAGE'];
const TYPES: Record<string, { label: string; icon: IconName }> = {
  CD: { label: 'Construction Drawing (CD)', icon: 'pen-tool' },
  DRONE_POINTCLOUD: { label: 'Drone LiDAR Point Cloud', icon: 'box' },
  DRONE_VIDEO: { label: '360° Orbit Video', icon: 'video' },
  MA_SA: { label: 'Mount & Structural Analysis', icon: 'bar-chart-2' },
  RFDS: { label: 'RF Data Sheet (RFDS)', icon: 'radio' },
  BOM_REV0: { label: 'REV 0 Preliminary BOM', icon: 'list' },
  DRONE_VENDOR: { label: 'Vendor Survey Measurements', icon: 'clipboard' },
  DRONE_META: { label: 'Drone Flight Metadata', icon: 'navigation' },
  DRONE_IMAGE: { label: 'Survey Photo / Orthophoto', icon: 'image' },
};
const typeRank = (t: string) => { const i = TYPE_ORDER.indexOf(t); return i < 0 ? 99 : i; };
const typeInfo = (t: string) => TYPES[t] ?? { label: humanize(t || 'OTHER'), icon: 'file' as IconName };

const fileIcon = (name: string): IconName =>
  /\.(jpe?g|png|tiff?)$/i.test(name) ? 'image'
    : /\.(mp4|mov|avi)$/i.test(name) ? 'film'
      : /\.(xlsx?|csv)$/i.test(name) ? 'grid'
        : /\.(laz|las|ply|e57)$/i.test(name) ? 'box'
          : /\.(dxf|dwg)$/i.test(name) ? 'pen-tool'
            : /\.(json|xml|kml)$/i.test(name) ? 'code'
              : 'file-text';

type Filter = 'ALL' | 'CURRENT' | 'SUPERSEDED' | 'DUPLICATE';
const STATUS: Record<string, { label: string; color: string }> = {
  CURRENT: { label: 'Picked', color: colors.ok },
  SUPERSEDED: { label: 'Superseded', color: colors.warn },
  DUPLICATE: { label: 'Duplicate', color: colors.neutral },
};
const statusInfo = (s?: string) => STATUS[s ?? ''] ?? { label: humanize(s || 'REGISTERED'), color: colors.neutral };

// ------------------------------------------------------------------ site header + information grid
function InfoCell({ icon, label, value, sub, missing, width, children }: {
  icon: IconName; label: string; value?: string | null; sub?: string | null; missing: string; width: string; children?: React.ReactNode;
}) {
  return (
    <View style={{ width: width as any, paddingRight: space(4), paddingVertical: space(2.5), flexDirection: 'row', gap: space(3) }}>
      <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }}>
        <Icon name={icon} size={15} color={colors.muted} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={{ fontSize: 11, fontWeight: '600', color: colors.muted, letterSpacing: 0.4, textTransform: 'uppercase' }}>{label}</Text>
        {value ? (
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text, marginTop: 3 }} numberOfLines={2} selectable>{value}</Text>
        ) : (
          <Text style={{ fontSize: 14, color: colors.faint, marginTop: 3 }}>{missing}</Text>
        )}
        {sub ? <Text style={{ fontSize: 12.5, color: colors.muted, marginTop: 1 }} numberOfLines={2}>{sub}</Text> : null}
        {children}
      </View>
    </View>
  );
}

function SiteInfo({ d }: { d: SiteDetail }) {
  const st = d.site;
  const run = d.last_run?.[0];
  const [w, setW] = useState(0);
  const cols = w >= 860 ? 3 : w >= 520 ? 2 : 1;
  const cellW = `${100 / cols}%`;
  const place = [st.ADDRESS, [st.CITY, [st.STATE, st.ZIP].filter(Boolean).join(' ')].filter(Boolean).join(', ')].filter(Boolean).join(', ');
  const structure = [st.STRUCTURE_TYPE, st.HEIGHT_FT ? `${Number(st.HEIGHT_FT).toLocaleString('en-US')} ft` : null].filter(Boolean).join(' · ');
  const coords = st.LATITUDE != null && st.LONGITUDE != null && st.LATITUDE !== '' && st.LONGITUDE !== ''
    ? `${Number(st.LATITUDE).toFixed(5)}, ${Number(st.LONGITUDE).toFixed(5)}` : null;

  return (
    <Card padded={false} style={{ overflow: 'hidden' }}>
      <View onLayout={(e) => setW(e.nativeEvent.layout.width)} style={{ padding: space(5), paddingBottom: space(4) }}>
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: space(4), flexWrap: 'wrap' }}>
          <View style={{ width: 44, height: 44, borderRadius: 10, backgroundColor: colors.soft, borderWidth: 1, borderColor: '#DBE7FE', alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="map-pin" size={20} color={colors.accent} />
          </View>
          <View style={{ flex: 1, minWidth: 220 }}>
            <Text style={{ fontSize: 20, fontWeight: '700', color: colors.text, letterSpacing: -0.3 }} selectable>{st.SITE_NAME || st.SITE_ID}</Text>
            <Text style={{ fontSize: 13.5, color: colors.muted, marginTop: 2 }} selectable>
              {[place, st.MARKET ? `${st.MARKET} market` : null].filter(Boolean).join('  ·  ') || 'Location not available'}
            </Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space(2), marginTop: space(3) }}>
              <Tag icon="hash" text={st.SITE_ID} mono />
              <Tag icon="layers" text={structure || 'Structure not available'} muted={!structure} />
              {st.SITE_STATUS ? <Tag icon="activity" text={st.SITE_STATUS} /> : null}
              {st.STRUCTURE_OWNER ? <Text style={{ fontSize: 12.5, color: colors.muted }} numberOfLines={1}>Owner: {st.STRUCTURE_OWNER}</Text> : null}
            </View>
          </View>
          <View style={{ alignItems: 'flex-end', gap: 4 }}>
            <Text style={{ fontSize: 11, fontWeight: '600', color: colors.muted, letterSpacing: 0.4, textTransform: 'uppercase' }}>Site status</Text>
            <Badge text={st.WORKFLOW_STATE || 'ASSIGNED'} color={colors.info} dot />
          </View>
        </View>
      </View>
      <View style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingHorizontal: space(5), paddingVertical: space(2.5), flexDirection: 'row', flexWrap: 'wrap', backgroundColor: '#FCFDFE' }}>
        <InfoCell width={cellW} icon="git-branch" label="Stream" value={st.STREAM ? humanize(st.STREAM) : null} sub={st.SERVICE_LINE} missing="Not assigned" />
        <InfoCell width={cellW} icon="briefcase" label="Project" value={st.PROJECT_NAME} sub={st.PROJECT_TYPE} missing="Not assigned" />
        <InfoCell width={cellW} icon="crosshair" label="Coordinates" value={coords} sub={coords ? 'Latitude, longitude' : null} missing="Not available" />
        <InfoCell width={cellW} icon="users" label="CX Service Provider" value={st.CX_SP} missing="Not assigned" />
        <InfoCell width={cellW} icon="list" label="Current BOM Revision" value={st.CURRENT_BOM_REV} missing="Not available" />
        <InfoCell width={cellW} icon="play-circle" label="Last Pipeline Run" value={run ? fmtDateTime(run.STARTED_AT) ?? run.STARTED_AT : null} missing="Not run yet">
          {run?.STATUS ? <View style={{ flexDirection: 'row', marginTop: 4 }}><Badge text={run.STATUS} dot /></View> : null}
        </InfoCell>
      </View>
    </Card>
  );
}

function Tag({ icon, text, mono, muted }: { icon: IconName; text: string; mono?: boolean; muted?: boolean }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.md, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border }}>
      <Icon name={icon} size={12} color={colors.muted} />
      <Text style={[{ fontSize: 12.5, fontWeight: '600', color: muted ? colors.faint : colors.text }, mono && web({ fontVariantNumeric: 'tabular-nums' })]} selectable>{text}</Text>
    </View>
  );
}

// ------------------------------------------------------------------ revision check
function Metric({ label, value, color, active, onPress }: { label: string; value: number; color: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: active }} accessibilityLabel={`${label}: ${value}. Show in the register`}
      style={({ hovered }: any) => [{ flexGrow: 1, flexBasis: 110, paddingVertical: space(2.5), paddingHorizontal: space(3.5), borderRadius: radius.lg, borderWidth: 1,
        borderColor: active ? colors.accent : hovered ? colors.borderStrong : colors.border, backgroundColor: active ? '#F8FBFF' : '#fff' },
        web({ cursor: 'pointer', transitionProperty: 'border-color', transitionDuration: '140ms' })]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: color }} />
        <Text style={{ fontSize: 11.5, fontWeight: '600', color: colors.muted }}>{label}</Text>
      </View>
      <Text style={[{ fontSize: 22, fontWeight: '700', color: colors.text, marginTop: 2, letterSpacing: -0.4 }, web({ fontVariantNumeric: 'tabular-nums' })]}>{value}</Text>
    </Pressable>
  );
}

function RevisionCheck({ d, counts, filter, setFilter }: { d: SiteDetail; counts: Record<Filter, number>; filter: Filter; setFilter: (f: Filter) => void }) {
  const check = d.revision_check;
  const [open, setOpen] = useState(false);
  const types = [...(check?.types ?? [])].sort((a: any, b: any) => typeRank(a.doc_type) - typeRank(b.doc_type));
  const hasDocs = counts.ALL > 0;
  const pickedPerType = useMemo(() => {
    const m: Record<string, number> = {};
    for (const x of d.documents ?? []) if (x.STATUS === 'CURRENT') m[x.DOC_TYPE] = (m[x.DOC_TYPE] ?? 0) + 1;
    return m;
  }, [d.documents]);
  return (
    <Card padded={false}>
      <View style={{ padding: space(5), gap: space(4) }}>
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: space(3), flexWrap: 'wrap' }}>
          <View style={{ width: 36, height: 36, borderRadius: 9, backgroundColor: hasDocs ? '#ECFDF5' : colors.surfaceAlt, borderWidth: 1, borderColor: hasDocs ? '#BBE5D6' : colors.border, alignItems: 'center', justifyContent: 'center' }}>
            <Icon name="shield" size={17} color={hasDocs ? colors.ok : colors.muted} />
          </View>
          <View style={{ flex: 1, minWidth: 220 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
              <Text style={{ fontSize: 15.5, fontWeight: '700', color: colors.text }}>Document revision check</Text>
              {hasDocs && check?.status ? <Badge text={check.status} color={colors.ok} /> : null}
            </View>
            <Text style={{ fontSize: 13, color: colors.muted, marginTop: 2 }}>
              {hasDocs ? (check?.message ?? 'Revision selection result for this site.') : 'No documents registered yet. The check runs when the pipeline ingests the site documents.'}
            </Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(2.5) }}>
          <Metric label="Total documents" value={counts.ALL} color={colors.accent} active={filter === 'ALL'} onPress={() => setFilter('ALL')} />
          <Metric label="Latest (picked)" value={counts.CURRENT} color={colors.ok} active={filter === 'CURRENT'} onPress={() => setFilter('CURRENT')} />
          <Metric label="Superseded" value={counts.SUPERSEDED} color={colors.warn} active={filter === 'SUPERSEDED'} onPress={() => setFilter('SUPERSEDED')} />
          <Metric label="Duplicate" value={counts.DUPLICATE} color={colors.neutral} active={filter === 'DUPLICATE'} onPress={() => setFilter('DUPLICATE')} />
        </View>
      </View>

      <Pressable onPress={() => setOpen((o) => !o)} accessibilityRole="button" accessibilityState={{ expanded: open }}
        style={({ hovered }: any) => [{ flexDirection: 'row', alignItems: 'center', gap: space(2), paddingHorizontal: space(5), paddingVertical: space(3),
          borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: hovered ? colors.surfaceAlt : '#FCFDFE' }, web({ cursor: 'pointer' })]}>
        <Icon name="info" size={14} color={colors.accent} />
        <Text style={{ flex: 1, fontSize: 13, fontWeight: '600', color: colors.text }}>How revisions are selected</Text>
        <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} color={colors.muted} />
      </Pressable>
      {open ? (
        <View style={{ paddingHorizontal: space(5), paddingBottom: space(5), paddingTop: space(1), backgroundColor: '#FCFDFE', gap: space(4) }}>
          <View style={{ gap: space(2) }}>
            {[
              'When two files have identical content, the first is kept and the other is marked Duplicate.',
              'For RF Data Sheets, Construction Drawings, Mount & Structural Analyses and the REV 0 BOM, the highest revision across all file formats is picked. Every lower revision is marked Superseded.',
              'Drone point clouds, video, photos, metadata and vendor surveys have no revisions, so each one is used.',
              'Pipeline checks run against the picked documents. Superseded and duplicate files stay in the register for reference.',
            ].map((t) => (
              <View key={t} style={{ flexDirection: 'row', gap: space(2) }}>
                <Icon name="check" size={14} color={colors.ok} />
                <Text style={{ flex: 1, fontSize: 13, color: colors.text, lineHeight: 19 }}>{t}</Text>
              </View>
            ))}
          </View>
          {types.length ? (
            <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, overflow: 'hidden', backgroundColor: '#fff' }}>
              {types.map((t: any, i: number) => (
                <View key={t.doc_type} style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space(3), paddingHorizontal: space(3.5), paddingVertical: space(2.5), borderTopWidth: i ? 1 : 0, borderTopColor: colors.border }}>
                  <Text style={{ width: 230, fontSize: 12.5, fontWeight: '600', color: colors.text }}>{typeInfo(t.doc_type).label}</Text>
                  <Text style={{ flex: 1, minWidth: 180, fontSize: 12.5, color: t.picked_file ? colors.text : colors.faint }} numberOfLines={1}>
                    {(pickedPerType[t.doc_type] ?? 0) > 1 ? `${pickedPerType[t.doc_type]} files picked` : t.picked_file ? `Picked: ${t.picked_file}` : 'No file picked'}
                  </Text>
                  <Text style={{ fontSize: 12, color: t.has_superseded ? colors.warn : colors.muted }}>
                    {t.has_superseded ? `Superseded: ${(t.superseded_revisions ?? []).join(', ')}` : `${t.total_files} file${t.total_files === 1 ? '' : 's'}`}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}
    </Card>
  );
}

// ------------------------------------------------------------------ document register
const COLS = { rev: 84, fmt: 130, date: 116, status: 112, act: 112 };

function DocRow({ x, wide, pickedRev, onPreview }: { x: R; wide: boolean; pickedRev?: string | null; onPreview: () => void }) {
  const stt = statusInfo(x.STATUS);
  const dim = x.STATUS === 'SUPERSEDED' || x.STATUS === 'DUPLICATE';
  const fmt = [x.FILE_FORMAT, size(x.SIZE_BYTES)].filter(Boolean).join(' · ') || 'Not available';
  const uploaded = fmtDate(x.REGISTERED_AT) ?? fmtDate(x.DOC_DATE) ?? 'Not available';
  const note = x.STATUS === 'SUPERSEDED' ? (pickedRev ? `Replaced by ${pickedRev}` : 'Replaced by a newer revision')
    : x.STATUS === 'DUPLICATE' ? 'Same content as another file in this site' : null;
  const rev = x.REVISION ? (
    <View style={{ alignSelf: 'flex-start', paddingHorizontal: 7, paddingVertical: 2, borderRadius: radius.sm, backgroundColor: dim ? colors.surfaceAlt : colors.soft, borderWidth: 1, borderColor: dim ? colors.border : '#DBE7FE' }}>
      <Text style={{ fontSize: 11.5, fontWeight: '700', color: dim ? colors.muted : colors.accent }}>{x.REVISION}</Text>
    </View>
  ) : null;
  const actions = (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(1.5), justifyContent: 'flex-end', width: wide ? COLS.act : undefined }}>
      <Button small kind="secondary" icon="eye" title="Preview" onPress={onPreview} />
      {x.DOC_ID ? (
        <Pressable onPress={() => Linking.openURL(authedUrl(`/documents/${x.DOC_ID}/download`))} accessibilityRole="button" accessibilityLabel={`Download ${x.FILE_NAME}`}
          style={({ hovered }: any) => [{ width: 30, height: 30, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', borderWidth: 1,
            borderColor: hovered ? colors.borderStrong : colors.border, backgroundColor: hovered ? colors.surfaceAlt : '#fff' }]}>
          <Icon name="download" size={14} color={colors.muted} />
        </Pressable>
      ) : null}
    </View>
  );
  const name = (
    <View style={{ flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: space(3) }}>
      <View style={{ width: 32, height: 32, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: dim ? colors.surfaceAlt : colors.soft }}>
        <Icon name={fileIcon(x.FILE_NAME ?? '')} size={15} color={dim ? colors.faint : colors.accent} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={{ fontSize: 13.5, fontWeight: '600', color: dim ? colors.muted : colors.text }} numberOfLines={1} selectable>{x.FILE_NAME}</Text>
        {note ? <Text style={{ fontSize: 12, color: x.STATUS === 'SUPERSEDED' ? colors.warn : colors.muted, marginTop: 1 }} numberOfLines={1}>{note}</Text> : null}
      </View>
    </View>
  );

  if (wide) {
    return (
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), paddingHorizontal: space(4), paddingVertical: space(2.5), borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: dim ? '#FCFCFD' : '#fff' }}>
        {name}
        <View style={{ width: COLS.rev }}>{rev ?? <Text style={{ fontSize: 12, color: colors.faint }}>None</Text>}</View>
        <Text style={{ width: COLS.fmt, fontSize: 12.5, color: colors.muted }} numberOfLines={1}>{fmt}</Text>
        <Text style={{ width: COLS.date, fontSize: 12.5, color: colors.muted }} numberOfLines={1}>{uploaded}</Text>
        <View style={{ width: COLS.status, flexDirection: 'row' }}><Badge text={stt.label} color={stt.color} dot /></View>
        {actions}
      </View>
    );
  }
  return (
    <View style={{ paddingHorizontal: space(4), paddingVertical: space(3), borderTopWidth: 1, borderTopColor: colors.border, gap: space(2), backgroundColor: dim ? '#FCFCFD' : '#fff' }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2) }}>
        {name}
        <Badge text={stt.label} color={stt.color} dot />
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: space(2), paddingLeft: 44 }}>
        {rev}
        <Text style={{ flex: 1, minWidth: 160, fontSize: 12, color: colors.muted }}>{fmt}  ·  Uploaded {uploaded}</Text>
        {actions}
      </View>
    </View>
  );
}

function Register({ d, docs, counts, filter, setFilter, onPreview }: {
  d: SiteDetail; docs: R[]; counts: Record<Filter, number>; filter: Filter; setFilter: (f: Filter) => void; onPreview: (x: R) => void;
}) {
  const { width: winW } = useWindowDimensions();
  const [w, setW] = useState(winW);
  const wide = w >= 900;
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const picked = useMemo(() => Object.fromEntries((d.revision_check?.types ?? []).map((t: any) => [t.doc_type, t.picked_revision])), [d.revision_check]);

  const groups = useMemo(() => {
    const by: Record<string, R[]> = {};
    for (const x of docs) (by[x.DOC_TYPE || 'OTHER'] ??= []).push(x);
    return Object.keys(by).sort((a, b) => typeRank(a) - typeRank(b) || a.localeCompare(b)).map((type) => ({ type, all: by[type], rows: by[type].filter((x) => filter === 'ALL' || x.STATUS === filter) }));
  }, [docs, filter]);
  const visible = groups.filter((g) => g.rows.length);
  const allCollapsed = visible.length > 0 && visible.every((g) => collapsed[g.type]);
  const toggleAll = () => setCollapsed(allCollapsed ? {} : Object.fromEntries(visible.map((g) => [g.type, true])));

  return (
    <Card padded={false} style={{ overflow: 'hidden' }}>
      <View onLayout={(e) => setW(e.nativeEvent.layout.width)} style={{ padding: space(5), paddingBottom: space(3.5), gap: space(3) }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 220 }}>
            <Text style={{ fontSize: 15.5, fontWeight: '700', color: colors.text }}>Documents & current revisions</Text>
            <Text style={{ fontSize: 13, color: colors.muted, marginTop: 2 }}>Every document registered for this site, grouped by type. Superseded and duplicate files stay available.</Text>
          </View>
          {visible.length ? <Button small kind="ghost" icon={allCollapsed ? 'chevrons-down' : 'chevrons-up'} title={allCollapsed ? 'Expand all' : 'Collapse all'} onPress={toggleAll} /> : null}
        </View>
        <Chips<Filter> value={filter} onChange={setFilter} options={[
          { key: 'ALL', label: 'All', count: counts.ALL },
          { key: 'CURRENT', label: 'Picked', count: counts.CURRENT },
          { key: 'SUPERSEDED', label: 'Superseded', count: counts.SUPERSEDED },
          { key: 'DUPLICATE', label: 'Duplicate', count: counts.DUPLICATE },
        ]} />
      </View>

      {docs.length === 0 ? (
        <View style={{ borderTopWidth: 1, borderTopColor: colors.border }}>
          <EmptyState icon="folder" title="No documents registered yet" text="Documents appear here once the pipeline ingests the site folder or files are uploaded." />
        </View>
      ) : visible.length === 0 ? (
        <View style={{ borderTopWidth: 1, borderTopColor: colors.border }}>
          <EmptyState icon="filter" title={`No ${statusInfo(filter).label.toLowerCase()} documents`} text="Choose another filter to see the rest of the register." />
        </View>
      ) : (
        <>
          {wide ? (
            <View style={{ flexDirection: 'row', gap: space(3), paddingHorizontal: space(4), paddingVertical: space(2), borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.surfaceAlt }}>
              {[['Document', 0], ['Revision', COLS.rev], ['Format · size', COLS.fmt], ['Uploaded', COLS.date], ['Status', COLS.status], ['', COLS.act]].map(([t, cw]) => (
                <Text key={t as string} style={[{ fontSize: 11, fontWeight: '600', color: colors.muted, letterSpacing: 0.4, textTransform: 'uppercase' }, cw ? { width: cw as number } : { flex: 1, paddingLeft: 44 }]}>{t}</Text>
              ))}
            </View>
          ) : null}
          {visible.map((g) => {
            const info = typeInfo(g.type);
            const isOpen = !collapsed[g.type];
            const nPicked = g.all.filter((x) => x.STATUS === 'CURRENT').length;
            const nOld = g.all.filter((x) => x.STATUS === 'SUPERSEDED').length;
            const nDup = g.all.filter((x) => x.STATUS === 'DUPLICATE').length;
            const pickedDoc = g.all.find((x) => x.STATUS === 'CURRENT' && x.REVISION);
            return (
              <View key={g.type}>
                <Pressable onPress={() => setCollapsed((c) => ({ ...c, [g.type]: isOpen }))} accessibilityRole="button" accessibilityState={{ expanded: isOpen }}
                  accessibilityLabel={`${info.label}, ${g.rows.length} document${g.rows.length === 1 ? '' : 's'}`}
                  style={({ hovered }: any) => [{ flexDirection: 'row', alignItems: 'center', gap: space(3), paddingHorizontal: space(4), paddingVertical: space(2.5),
                    borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: hovered ? '#F1F5FA' : '#F8FAFC' }, web({ cursor: 'pointer' })]}>
                  <Icon name={isOpen ? 'chevron-down' : 'chevron-right'} size={16} color={colors.muted} />
                  <Icon name={info.icon} size={15} color={colors.navy} />
                  <Text style={{ fontSize: 13.5, fontWeight: '700', color: colors.text, flexShrink: 1 }} numberOfLines={1}>{info.label}</Text>
                  <View style={{ paddingHorizontal: 7, paddingVertical: 1, borderRadius: radius.pill, backgroundColor: '#fff', borderWidth: 1, borderColor: colors.border }}>
                    <Text style={{ fontSize: 11.5, fontWeight: '600', color: colors.muted }}>{g.rows.length}</Text>
                  </View>
                  <View style={{ flex: 1 }} />
                  {wide ? (
                    <Text style={{ fontSize: 12, color: colors.muted }} numberOfLines={1}>
                      {[pickedDoc ? `Picked ${picked[g.type] ?? pickedDoc.REVISION}` : nPicked ? `${nPicked} picked` : null, nOld ? `${nOld} superseded` : null, nDup ? `${nDup} duplicate` : null].filter(Boolean).join('  ·  ')}
                    </Text>
                  ) : null}
                </Pressable>
                {isOpen ? g.rows.map((x) => (
                  <DocRow key={x.DOC_ID || x.FILE_NAME} x={x} wide={wide} pickedRev={pickedDoc ? (picked[g.type] ?? pickedDoc.REVISION) : null} onPreview={() => onPreview(x)} />
                )) : null}
              </View>
            );
          })}
        </>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ screen
export function Overview({ d }: { d: SiteDetail; reload: () => void }) {
  const { can } = useAuth();
  const st = d.site;
  const docs = d.documents ?? [];
  const check = d.revision_check;
  const [filter, setFilter] = useState<Filter>('ALL');
  const [previewTarget, setPreviewTarget] = useState<FilePreviewTarget | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<ApiError | null>(null);

  // counts of the statuses the backend assigned (the revision check's own numbers where it gives them)
  const counts: Record<Filter, number> = {
    ALL: check?.total_documents ?? docs.length,
    CURRENT: check?.latest_picked_count ?? docs.filter((x) => x.STATUS === 'CURRENT').length,
    SUPERSEDED: check?.superseded_count ?? docs.filter((x) => x.STATUS === 'SUPERSEDED').length,
    DUPLICATE: docs.filter((x) => x.STATUS === 'DUPLICATE').length,
  };

  const deleteSite = async () => {
    setConfirmDelete(false);
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.del(`/sites/${encodeURIComponent(st.SITE_ID)}`);
      mutateApi('/sites');
      mutateApi('/sharepoint/sites');
      mutateApi('/sites/dashboard');
      router.replace('/(tabs)/sites');
    } catch (e) {
      setDeleteError(e as ApiError);
      setDeleting(false);
    }
  };

  return (
    <View style={{ gap: space(4) }}>
      <SiteInfo d={d} />
      <RevisionCheck d={d} counts={counts} filter={filter} setFilter={setFilter} />
      <Register d={d} docs={docs} counts={counts} filter={filter} setFilter={setFilter}
        onPreview={(x) => setPreviewTarget({ name: x.FILE_NAME, docId: x.DOC_ID, siteId: st.SITE_ID, size: x.SIZE_BYTES })} />

      {can('ADMIN') ? (
        <View style={[{ borderWidth: 1, borderColor: '#FECACA', borderRadius: radius.xl, backgroundColor: '#fff', padding: space(4), marginTop: space(2) }, shadow]}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: space(3) }}>
            <View style={{ flex: 1, minWidth: 220, gap: 2 }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: colors.danger }}>Delete site</Text>
              <Text style={{ fontSize: 12.5, color: colors.muted }}>
                Permanently deletes {st.SITE_ID}, including all registered documents, pipeline run history, discrepancies, redlines and files.
              </Text>
            </View>
            <Button title={deleting ? 'Deleting...' : 'Delete site'} kind="danger" small icon="trash-2" disabled={deleting} onPress={() => setConfirmDelete(true)} />
          </View>
          {deleteError ? <View style={{ marginTop: space(3) }}><ErrorView error={deleteError} /></View> : null}
        </View>
      ) : null}

      <ConfirmDialog open={confirmDelete} danger title={`Delete site ${st.SITE_ID}?`} confirmText="Delete site"
        message="All documents, pipeline run history, discrepancies, redlines and files will be permanently removed from the database and disk. This cannot be undone."
        onConfirm={deleteSite} onCancel={() => setConfirmDelete(false)} />
      <FilePreviewModal target={previewTarget} onClose={() => setPreviewTarget(null)} />
    </View>
  );
}
