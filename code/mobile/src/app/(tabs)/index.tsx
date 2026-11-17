// Dashboard: operational overview for the signed-in persona's sites (a CX SP sees only its own sites).
// Every number and row comes from the API: /sites/dashboard, /sites, /pipeline/runs, /redlines, /rfis,
// /discrepancies and (for roles allowed to read it) /audit. Nothing is estimated or invented.
import { Feather } from '@expo/vector-icons';
import { Redirect, router, useFocusEffect } from 'expo-router';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View, useWindowDimensions } from 'react-native';
import { elapsed, RUN_STATE, runState, STAGES, STATE, stageState } from '../../components/site/pipeline/model';
import { colors, font, radius, space, tint } from '../../components/theme';
import { Badge, Button, Chips, EmptyState, ErrorView, IconName, Loading, s, SearchBox, Skeleton } from '../../components/ui';
import { useAuth } from '../../lib/auth';
import { roleLabel, when } from '../../lib/format';
import { PipelineRun, PipelineStep, Row } from '../../lib/types';
import { useApi } from '../../lib/useApi';

interface Dash {
  sites: number; by_state: Record<string, number>; by_stream: Record<string, number>;
  discrepancies: { total: number; by_status: Record<string, number>; by_outcome: Record<string, number>; by_severity: Record<string, number> };
  redlines: Record<string, number>; rfis: Record<string, number>; ehs_open: number; estimate_total_usd: number; inbox_unread: number;
}

const REDLINE_DONE = new Set(['COMPLETED', 'REJECTED', 'INCORPORATED', 'REMOVED', 'CLOSED']);
const RFI_DONE = new Set(['ANSWERED', 'CLOSED']);
const isPipelineRun = (r: PipelineRun) => r.RUN_ID?.startsWith('RUN-');
const stepsOf = (r?: PipelineRun | null): PipelineStep[] => (r && Array.isArray(r.STEPS) ? (r.STEPS as PipelineStep[]) : []);
/** The stage a run is at: the running or failed one, else the last that ran (a stop after stage 4 reads as stage 4). */
function currentStage(r: PipelineRun) {
  const st = stepsOf(r);
  const i = Math.max(st.findIndex((x) => x.status === 'RUNNING'), st.findIndex((x) => x.status === 'FAILED'));
  const idx = i >= 0 ? i : st.reduce((a, x, k) => (x.status === 'DONE' ? k : a), -1);
  return idx >= 0 ? { n: idx + 1, title: STAGES[idx]?.title ?? st[idx].label, state: stageState(st, idx), done: st.filter((x) => x.status === 'DONE').length, total: st.length || 6 } : null;
}

// ------------------------------------------------------------------ building blocks
function Panel({ title, subtitle, icon, action, children, style, padded = true }: { title: string; subtitle?: string; icon?: IconName; action?: React.ReactNode; children: React.ReactNode; style?: any; padded?: boolean }) {
  return (
    <View style={[{ backgroundColor: '#fff', borderRadius: 14, borderWidth: 1, borderColor: colors.border, overflow: 'hidden', boxShadow: '0 1px 2px rgba(16,24,40,0.04)' } as any, style]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), paddingHorizontal: space(5), paddingTop: space(4), paddingBottom: space(3), flexWrap: 'wrap' }}>
        {icon ? <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: tint.info.bg, alignItems: 'center', justifyContent: 'center' }}><Feather name={icon} size={15} color={colors.accent} /></View> : null}
        <View style={{ flex: 1, minWidth: 180 }}>
          <Text style={{ fontSize: 15, fontWeight: '600', color: colors.text }}>{title}</Text>
          {subtitle ? <Text style={{ fontSize: 12.5, color: colors.muted, marginTop: 1 }}>{subtitle}</Text> : null}
        </View>
        {action}
      </View>
      <View style={padded ? { paddingHorizontal: space(5), paddingBottom: space(5) } : undefined}>{children}</View>
    </View>
  );
}

function Kpi({ label, value, icon, tone, hint, onPress, loading }: { label: string; value: React.ReactNode; icon: IconName; tone?: string; hint?: string; onPress?: () => void; loading?: boolean }) {
  return (
    <Pressable onPress={onPress} disabled={!onPress} accessibilityRole={onPress ? 'button' : undefined}
      style={({ hovered }: any) => [{ flexGrow: 1, flexBasis: 150, minWidth: 0, backgroundColor: '#fff', borderRadius: 14, borderWidth: 1, borderColor: hovered && onPress ? colors.borderStrong : colors.border, padding: space(4.5) },
        hovered && onPress ? ({ boxShadow: '0 4px 14px rgba(16,24,40,0.07)' } as any) : null]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text style={{ fontSize: 12.5, color: colors.muted, fontWeight: '500' }}>{label}</Text>
        <View style={{ width: 30, height: 30, borderRadius: 8, backgroundColor: tone ? tone + '14' : colors.surfaceAlt, alignItems: 'center', justifyContent: 'center' }}>
          <Feather name={icon} size={15} color={tone ?? colors.muted} />
        </View>
      </View>
      {loading ? <Skeleton width={60} height={26} style={{ marginTop: 8 }} /> : <Text style={{ fontSize: 28, fontWeight: '600', color: colors.text, letterSpacing: -0.6, marginTop: 4 }}>{value}</Text>}
      {hint ? <Text style={{ fontSize: 12, color: colors.faint, marginTop: 2 }} numberOfLines={1}>{hint}</Text> : null}
    </Pressable>
  );
}

function StageProgress({ r }: { r: PipelineRun }) {
  const st = stepsOf(r);
  return (
    <View style={{ flexDirection: 'row', gap: 3 }} accessibilityLabel={`${st.filter((x) => x.status === 'DONE').length} of ${st.length} stages completed`}>
      {(st.length ? st : Array.from({ length: 6 })).map((_, i) => {
        const v = st.length ? STATE[stageState(st, i)] : STATE.PENDING;
        const solid = st.length && ['COMPLETED', 'REVIEW', 'RUNNING', 'FAILED'].includes(stageState(st, i));
        return <View key={i} style={{ flex: 1, height: 5, borderRadius: 3, backgroundColor: solid ? v.color : '#E2E8F0' }} />;
      })}
    </View>
  );
}

const Th = ({ children, w, flex, right }: { children: string; w?: number; flex?: number; right?: boolean }) => (
  <Text style={{ width: w, flex: w ? undefined : flex ?? 1, fontSize: 11, fontWeight: '600', color: colors.muted, letterSpacing: 0.4, textTransform: 'uppercase', textAlign: right ? 'right' : 'left', paddingHorizontal: space(2) }} numberOfLines={1}>{children}</Text>
);

// ------------------------------------------------------------------ screen
type SiteFilter = 'ALL' | 'RUNNING' | 'COMPLETED' | 'FINDINGS' | 'STOPPED' | 'FAILED' | 'NOT_STARTED';

export default function Dashboard() {
  const { user, can } = useAuth();
  const { width } = useWindowDimensions();
  const isAe = user?.role === 'AE_ENGINEER';
  const canAudit = can('REVIEWER', 'ERICSSON');                 // /audit is open to Admin, Reviewer and Ericsson
  const canRedlines = can('AE_ENGINEER');                       // Admin or A&E may open Redlines & RFIs (same rule as the sidebar)
  const d = useApi<Dash>(isAe ? null : '/sites/dashboard');
  const sites = useApi<Row[]>(isAe ? null : '/sites');
  const runs = useApi<PipelineRun[]>(isAe ? null : '/pipeline/runs?limit=300');
  const redlines = useApi<Row[]>(isAe ? null : '/redlines');
  const rfis = useApi<Row[]>(isAe ? null : '/rfis');
  const discs = useApi<Row[]>(isAe ? null : '/discrepancies?status=OPEN');
  const audit = useApi<Row[]>(isAe || !canAudit ? null : '/audit?limit=120');
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState<SiteFilter>('ALL');

  const reloadAll = useCallback((silent = false) => {
    for (const x of [d, sites, runs, redlines, rfis, discs, audit]) void x.reload(silent);
  }, [d, sites, runs, redlines, rfis, discs, audit]);
  const firstFocus = useRef(true);
  useFocusEffect(useCallback(() => {
    if (firstFocus.current) { firstFocus.current = false; return; }
    reloadAll(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []));

  const pipelineRuns = useMemo(() => (runs.data ?? []).filter(isPipelineRun), [runs.data]);
  const latest = useMemo(() => {
    const m = new Map<string, PipelineRun>();
    for (const r of pipelineRuns) if (!m.has(r.SITE_ID)) m.set(r.SITE_ID, r);
    return m;
  }, [pipelineRuns]);
  const siteName = useMemo(() => Object.fromEntries((sites.data ?? []).map((x) => [x.SITE_ID, x.SITE_NAME])), [sites.data]);
  const openRed = useMemo(() => (redlines.data ?? []).filter((x) => !REDLINE_DONE.has(x.STATUS)), [redlines.data]);
  const openRfi = useMemo(() => (rfis.data ?? []).filter((x) => !RFI_DONE.has(x.STATUS)), [rfis.data]);
  const perSite = useMemo(() => {
    const m: Record<string, { red: number; rfi: number }> = {};
    for (const x of openRed) (m[x.SITE_ID] ??= { red: 0, rfi: 0 }).red += 1;
    for (const x of openRfi) (m[x.SITE_ID] ??= { red: 0, rfi: 0 }).rfi += 1;
    return m;
  }, [openRed, openRfi]);

  const siteRows = useMemo(() => (sites.data ?? []).map((x) => {
    const r = latest.get(x.SITE_ID);
    return { site: x, run: r, state: runState(r ?? null, r ? stepsOf(r) : null) };
  }), [sites.data, latest]);
  const siteCounts = useMemo(() => siteRows.reduce<Record<string, number>>((a, x) => ({ ...a, [x.state]: (a[x.state] ?? 0) + 1, ALL: (a.ALL ?? 0) + 1 }), {}), [siteRows]);
  const shownSites = siteRows.filter((x) => (filter === 'ALL' || x.state === filter)
    && (!q || `${x.site.SITE_ID} ${x.site.SITE_NAME ?? ''} ${x.site.CITY ?? ''}`.toLowerCase().includes(q.toLowerCase())));

  if (isAe) return <Redirect href="/(tabs)/rfis" />;

  const active = pipelineRuns.filter((r) => r.STATUS === 'RUNNING').length;
  const fullyCompleted = pipelineRuns.filter((r) => r.STATUS !== 'RUNNING' && r.STATUS !== 'FAILED' && stepsOf(r).length > 0 && stepsOf(r).every((x) => x.status === 'DONE')).length;
  const pending = d.data?.discrepancies.by_status.OPEN ?? discs.data?.length ?? 0;
  const wide = width >= 1200;
  const loadingAny = !d.data && !d.error;

  // engineering review queue, from the lists themselves
  const aeQueue = [...openRfi.filter((x) => x.TO_PARTY === 'AE_ENGINEER'), ...openRed.filter((x) => ['WORK_QUEUE', 'ACKNOWLEDGED', 'SENT_TO_AE'].includes(x.STATUS))];
  const adminQueue = openRfi.filter((x) => x.TO_PARTY !== 'AE_ENGINEER');
  const reviewItems = [
    ...openRed.map((x) => ({ key: x.REDLINE_ID, kind: 'Redline', site: x.SITE_ID, title: x.MARKUP, status: x.STATUS, who: x.REVIEWED_BY ? `Reviewed by ${x.REVIEWED_BY}` : x.SUBMITTED_BY ? `Submitted by ${x.SUBMITTED_BY}` : null, at: x.UPDATED_AT ?? x.CREATED_AT })),
    ...openRfi.map((x) => ({ key: x.RFI_ID, kind: 'RFI', site: x.SITE_ID, title: x.SUBJECT, status: x.STATUS, who: x.TO_PARTY === 'AE_ENGINEER' ? 'To A&E Engineer' : 'To Admin / Ericsson', at: x.UPDATED_AT ?? x.CREATED_AT })),
    ...(discs.data ?? []).map((x) => ({ key: x.DISC_ID, kind: 'Finding', site: x.SITE_ID, title: x.TITLE, status: x.STATUS, who: x.ASSIGNED_TO ? `Assigned to ${x.ASSIGNED_TO}` : null, at: x.UPDATED_AT ?? x.CREATED_AT })),
  ].sort((a, b) => String(b.at ?? '').localeCompare(String(a.at ?? '')));

  // recent activity: audit entries (no sign-ins) plus pipeline run start/finish from the runs table
  const activity = [
    ...(audit.data ?? []).filter((a) => a.ENTITY_TYPE !== 'SESSION').map((a) => ({
      t: a.EVENT_TS, site: a.SITE_ID, who: a.ACTOR_USER_ID,
      icon: (a.ENTITY_TYPE === 'SHAREPOINT_FILE' ? 'upload-cloud' : a.ENTITY_TYPE === 'SITE' ? 'map-pin' : a.ENTITY_TYPE === 'DISCREPANCY' ? 'alert-triangle' : a.ENTITY_TYPE === 'REDLINE' ? 'edit-3' : a.ENTITY_TYPE === 'RFI' ? 'help-circle' : 'refresh-cw') as IconName,
      text: a.ENTITY_TYPE === 'SHAREPOINT_FILE' ? `Document uploaded: ${a.ENTITY_ID}` : a.ENTITY_TYPE === 'SITE' && a.ACTION === 'CREATE' ? `Site created: ${a.ENTITY_ID}`
        : a.ACTION === 'TRANSITION' ? `${a.ENTITY_TYPE === 'SITE_SCOPING' ? 'Site workflow' : a.ENTITY_TYPE === 'DISCREPANCY' ? 'Finding' : String(a.ENTITY_TYPE).replace(/_/g, ' ').toLowerCase()} status updated${(a.AFTER_VALUE?.WORKFLOW_STATE ?? a.AFTER_VALUE?.STATUS) ? ` to ${String(a.AFTER_VALUE.WORKFLOW_STATE ?? a.AFTER_VALUE.STATUS).replace(/_/g, ' ').toLowerCase()}` : ''}`
        : `${String(a.ACTION).toLowerCase()} ${String(a.ENTITY_TYPE).replace(/_/g, ' ').toLowerCase()}`,
    })),
    ...pipelineRuns.slice(0, 40).flatMap((r) => [
      { t: r.STARTED_AT, site: r.SITE_ID, who: r.TRIGGERED_BY, icon: 'play' as IconName, text: 'Pipeline execution started' },
      ...(r.FINISHED_AT ? [{ t: r.FINISHED_AT, site: r.SITE_ID, who: r.TRIGGERED_BY, icon: 'flag' as IconName, text: `Pipeline ${RUN_STATE[runState(r, stepsOf(r))].label.toLowerCase()}` }] : []),
    ]),
  ].filter((e) => e.t).sort((a, b) => String(b.t).localeCompare(String(a.t))).slice(0, 12);

  const openSite = (id: string, tab?: string) => router.push({ pathname: '/site/[id]', params: tab ? { id, tab } : { id } });

  return (
    <ScrollView style={s.screen} contentContainerStyle={[s.content, { maxWidth: 1480, width: '100%', alignSelf: 'center' }]}
      refreshControl={<RefreshControl refreshing={d.loading && !!d.data} onRefresh={() => reloadAll()} />}>
      {/* header */}
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: space(4), flexWrap: 'wrap', marginBottom: space(5) }}>
        <View style={{ flexShrink: 1, minWidth: 260 }}>
          <Text style={{ fontSize: 12, fontWeight: '600', color: colors.accent, marginBottom: 4 }}>{`Signed in as ${roleLabel(user?.role)}`}</Text>
          <Text style={{ fontSize: 24, fontWeight: '600', color: colors.text, letterSpacing: -0.4 }}>Scoping operations</Text>
          <Text style={{ fontSize: 14, color: colors.muted, marginTop: 4 }}>Site progress, pipeline runs and engineering reviews across your sites.</Text>
        </View>
        <View style={{ flexDirection: 'row', gap: space(2), flexWrap: 'wrap', maxWidth: '100%', flexShrink: 1 }}>
          <Button kind="secondary" icon="rotate-cw" title="Refresh" onPress={() => reloadAll()} />
          <Button kind="secondary" icon="map-pin" title="All sites" onPress={() => router.push('/(tabs)/sites')} />
          {can('ADMIN') ? <Button icon="upload-cloud" title="Add documents" onPress={() => router.push('/(tabs)/sharepoint')} /> : null}
        </View>
      </View>
      {d.error ? <ErrorView error={d.error} onRetry={d.reload} /> : null}

      {/* A. KPIs */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(3), marginBottom: space(5) }}>
        <Kpi label="Total sites" icon="map-pin" value={d.data?.sites ?? '–'} loading={loadingAny} tone={colors.accent}
          hint={sites.data ? `${siteCounts.NOT_STARTED ?? 0} not run yet` : undefined} onPress={() => router.push('/(tabs)/sites')} />
        <Kpi label="Active pipeline runs" icon="activity" value={runs.data ? active : '–'} loading={!runs.data && !runs.error} tone={active ? colors.info : undefined} hint={active ? 'Running now' : 'No run in progress'} />
        <Kpi label="Fully completed runs" icon="check-circle" value={runs.data ? fullyCompleted : '–'} loading={!runs.data && !runs.error} tone={colors.ok}
          hint={runs.data ? `All six stages done · of ${pipelineRuns.length} runs` : undefined} />
        <Kpi label="Pending reviews" icon="clipboard" value={pending} loading={loadingAny} tone={pending ? colors.warn : undefined} hint="Open findings awaiting a decision"
          onPress={() => router.push('/(tabs)/queue')} />
        <Kpi label="Open redlines · RFIs" icon="edit-3" value={redlines.data && rfis.data ? `${openRed.length} · ${openRfi.length}` : '–'} loading={!redlines.data && !redlines.error}
          tone={openRed.length + openRfi.length ? colors.warn : undefined} hint={openRfi.some((x) => x.STATUS === 'DRAFT') ? `${openRfi.filter((x) => x.STATUS === 'DRAFT').length} RFI drafts not yet sent` : 'Not yet completed or answered'} onPress={canRedlines ? () => router.push('/(tabs)/rfis') : () => router.push('/(tabs)/queue')} />
      </View>

      {/* B + D */}
      <View style={{ flexDirection: wide ? 'row' : 'column', gap: space(4), alignItems: 'flex-start', marginBottom: space(4) }}>
        <Panel title="Site scoping overview" subtitle="Latest pipeline run of each site" icon="map" style={{ flex: wide ? 1.7 : undefined, width: wide ? undefined : '100%' }} padded={false}
          action={<Button small kind="ghost" title="Sites" iconRight="arrow-right" onPress={() => router.push('/(tabs)/sites')} />}>
          <View style={{ paddingHorizontal: space(5), gap: space(3), paddingBottom: space(3) }}>
            <SearchBox value={q} onChangeText={setQ} placeholder="Search site ID, name or city" />
            <Chips<SiteFilter> value={filter} onChange={setFilter} options={[
              { key: 'ALL', label: 'All', count: siteCounts.ALL ?? 0 }, { key: 'RUNNING', label: 'Running', count: siteCounts.RUNNING ?? 0 },
              { key: 'COMPLETED', label: 'Completed', count: siteCounts.COMPLETED ?? 0 }, { key: 'FINDINGS', label: 'With findings', count: siteCounts.FINDINGS ?? 0 },
              { key: 'STOPPED', label: 'Stopped', count: siteCounts.STOPPED ?? 0 }, { key: 'FAILED', label: 'Failed', count: siteCounts.FAILED ?? 0 },
              { key: 'NOT_STARTED', label: 'Not run', count: siteCounts.NOT_STARTED ?? 0 }]} />
          </View>
          {sites.error ? <View style={{ padding: space(5) }}><ErrorView error={sites.error} onRetry={sites.reload} /></View> : !sites.data ? <View style={{ padding: space(5) }}><Loading rows={5} /></View> : shownSites.length === 0 ? (
            <EmptyState icon="map-pin" title="No sites match" text={siteRows.length ? 'Change the search or the filter.' : 'No sites are assigned to you yet.'} />
          ) : (
            <View>
              {width >= 760 ? (
                <View style={{ flexDirection: 'row', paddingHorizontal: space(3), paddingVertical: space(2), backgroundColor: colors.surfaceAlt, borderTopWidth: 1, borderBottomWidth: 1, borderColor: colors.border }}>
                  <Th flex={1.3}>Site</Th><Th flex={1.4}>Current stage</Th><Th w={170}>Status</Th><Th w={130}>Last run</Th><Th w={96} right>Open items</Th>
                </View>
              ) : null}
              {shownSites.slice(0, 10).map(({ site, run, state }, i) => {
                const cur = run ? currentStage(run) : null;
                const rv = RUN_STATE[state];
                const open = perSite[site.SITE_ID];
                return (
                  <Pressable key={site.SITE_ID} onPress={() => openSite(site.SITE_ID)} accessibilityRole="button" accessibilityLabel={`Site ${site.SITE_ID}, ${rv.label}`}
                    style={({ hovered }: any) => ({ flexDirection: width >= 760 ? 'row' : 'column', alignItems: width >= 760 ? 'center' : 'stretch', gap: width >= 760 ? 0 : 6, paddingHorizontal: space(3), paddingVertical: space(3),
                      borderBottomWidth: i === Math.min(shownSites.length, 10) - 1 ? 0 : 1, borderBottomColor: colors.border, backgroundColor: hovered ? colors.surfaceAlt : '#fff' })}>
                    <View style={{ flex: 1.3, paddingHorizontal: space(2), minWidth: 0 }}>
                      <Text style={{ fontSize: 13.5, fontWeight: '600', color: colors.text }}>{site.SITE_ID}</Text>
                      <Text style={{ fontSize: 12, color: colors.muted }} numberOfLines={1}>{[site.SITE_NAME, site.CITY].filter(Boolean).join(' · ') || '—'}</Text>
                    </View>
                    <View style={{ flex: 1.4, paddingHorizontal: space(2), gap: 6, minWidth: 0 }}>
                      <Text style={{ fontSize: 12.5, color: cur ? colors.text : colors.faint }} numberOfLines={1}>{cur ? `${cur.n}. ${cur.title}` : 'Not run yet'}</Text>
                      {run ? <StageProgress r={run} /> : null}
                    </View>
                    <View style={{ width: width >= 760 ? 170 : undefined, paddingHorizontal: space(2) }}><Badge text={rv.label} color={rv.color} dot /></View>
                    <Text style={{ width: width >= 760 ? 130 : undefined, paddingHorizontal: space(2), fontSize: 12.5, color: run ? colors.text : colors.faint }}>{run ? when(run.STARTED_AT) : 'Never'}</Text>
                    <View style={{ width: width >= 760 ? 96 : undefined, paddingHorizontal: space(2), alignItems: width >= 760 ? 'flex-end' : 'flex-start' }}>
                      {open ? <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.warn }}>{`${open.red} RL · ${open.rfi} RFI`}</Text> : <Text style={{ fontSize: 12.5, color: colors.faint }}>—</Text>}
                    </View>
                  </Pressable>
                );
              })}
              {shownSites.length > 10 ? (
                <Pressable onPress={() => router.push('/(tabs)/sites')} style={({ hovered }: any) => ({ padding: space(3), alignItems: 'center', borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: hovered ? colors.surfaceAlt : '#fff' })}>
                  <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.accent }}>{`View all ${shownSites.length} sites`}</Text>
                </Pressable>
              ) : null}
            </View>
          )}
        </Panel>

        <Panel title="Engineering review queue" subtitle="Open items waiting for a person" icon="clipboard" style={{ flex: wide ? 1 : undefined, width: wide ? undefined : '100%' }}
          action={<Button small kind="ghost" title={canRedlines ? 'Redlines & RFIs' : 'Work queue'} iconRight="arrow-right" onPress={() => router.push(canRedlines ? '/(tabs)/rfis' : '/(tabs)/queue')} />}>
          {redlines.error && rfis.error ? <ErrorView error={redlines.error} onRetry={() => { void redlines.reload(); void rfis.reload(); }} /> : !redlines.data || !rfis.data ? <Loading rows={4} /> : (
            <>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(2), marginBottom: space(4) }}>
                {[{ l: 'Pending redlines', v: openRed.length, i: 'edit-3' as IconName }, { l: openRfi.some((x) => x.STATUS === 'DRAFT') ? `Open RFIs (${openRfi.filter((x) => x.STATUS === 'DRAFT').length} drafts)` : 'Open RFIs', v: openRfi.length, i: 'help-circle' as IconName },
                  { l: 'Awaiting A&E', v: aeQueue.length, i: 'tool' as IconName }, { l: 'Awaiting Admin / Ericsson', v: adminQueue.length, i: 'briefcase' as IconName }].map((m) => (
                  <View key={m.l} style={{ flexGrow: 1, flexBasis: 130, padding: space(3), borderRadius: 10, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Feather name={m.i} size={12} color={colors.muted} /><Text style={{ fontSize: 11.5, color: colors.muted }} numberOfLines={1}>{m.l}</Text></View>
                    <Text style={{ fontSize: 20, fontWeight: '600', color: m.v ? colors.text : colors.faint, marginTop: 2 }}>{m.v}</Text>
                  </View>
                ))}
              </View>
              {reviewItems.length === 0 ? <EmptyState icon="check-circle" title="Nothing waiting for review" /> : reviewItems.slice(0, 6).map((it, i) => (
                <Pressable key={it.key} onPress={() => (it.kind === 'Finding' ? router.push({ pathname: '/discrepancy/[id]', params: { id: it.key } }) : openSite(it.site, 'redlines'))}
                  style={({ hovered }: any) => ({ flexDirection: 'row', gap: space(3), paddingVertical: space(2.5), paddingHorizontal: space(2), marginHorizontal: -space(2), borderRadius: radius.md,
                    borderTopWidth: i ? 1 : 0, borderTopColor: colors.border, backgroundColor: hovered ? colors.surfaceAlt : 'transparent' })}>
                  <View style={{ width: 28, height: 28, borderRadius: 7, alignItems: 'center', justifyContent: 'center', backgroundColor: it.kind === 'RFI' ? tint.info.bg : it.kind === 'Redline' ? tint.warn.bg : tint.danger.bg }}>
                    <Feather name={it.kind === 'RFI' ? 'help-circle' : it.kind === 'Redline' ? 'edit-3' : 'alert-triangle'} size={13} color={it.kind === 'RFI' ? tint.info.fg : it.kind === 'Redline' ? tint.warn.fg : tint.danger.fg} />
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={{ fontSize: 13, color: colors.text }} numberOfLines={1}>{it.title}</Text>
                    <Text style={{ fontSize: 11.5, color: colors.muted, marginTop: 1 }} numberOfLines={1}>{[it.kind, it.site, it.who].filter(Boolean).join('  ·  ')}</Text>
                  </View>
                  <Badge text={it.status} />
                </Pressable>
              ))}
            </>
          )}
        </Panel>
      </View>

      {/* C. recent pipeline executions */}
      <Panel title="Recent pipeline executions" subtitle="Six stages: ingest, extract, reconcile, redlines & RFIs, RFDS & MA/SA, BOM" icon="git-branch" padded={false} style={{ marginBottom: space(4) }}>
        {runs.error ? <View style={{ padding: space(5) }}><ErrorView error={runs.error} onRetry={runs.reload} /></View> : !runs.data ? <View style={{ padding: space(5) }}><Loading rows={5} /></View> : pipelineRuns.length === 0 ? (
          <EmptyState icon="git-commit" title="No pipeline runs yet" text="Open a site and run the pipeline." />
        ) : (
          <ScrollView horizontal showsHorizontalScrollIndicator={width < 1100} contentContainerStyle={{ minWidth: '100%' as any }}>
            <View style={{ minWidth: 1040, flex: 1 }}>
              <View style={{ flexDirection: 'row', paddingHorizontal: space(3), paddingVertical: space(2), backgroundColor: colors.surfaceAlt, borderTopWidth: 1, borderBottomWidth: 1, borderColor: colors.border }}>
                <Th flex={1.2}>Site</Th><Th flex={1.3}>Run ID</Th><Th flex={1.5}>Current stage</Th><Th w={190}>Status</Th><Th w={90}>Duration</Th><Th w={130}>Started</Th><Th w={130}>Completed</Th><Th w={70} right> </Th>
              </View>
              {pipelineRuns.slice(0, 8).map((r, i, a) => {
                const cur = currentStage(r);
                const rv = RUN_STATE[runState(r, stepsOf(r))];
                const skipped = stepsOf(r).filter((x) => x.status === 'SKIPPED').length;
                return (
                  <Pressable key={r.RUN_ID} onPress={() => openSite(r.SITE_ID, 'pipeline')} accessibilityRole="button"
                    style={({ hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', paddingHorizontal: space(3), paddingVertical: space(3), borderBottomWidth: i === a.length - 1 ? 0 : 1, borderBottomColor: colors.border, backgroundColor: hovered ? colors.surfaceAlt : '#fff' })}>
                    <View style={{ flex: 1.2, paddingHorizontal: space(2), minWidth: 0 }}>
                      <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{r.SITE_ID}</Text>
                      <Text style={{ fontSize: 11.5, color: colors.muted }} numberOfLines={1}>{siteName[r.SITE_ID] ?? ''}</Text>
                    </View>
                    <Text style={{ flex: 1.3, paddingHorizontal: space(2), fontFamily: font.mono, fontSize: 11.5, color: colors.muted }} numberOfLines={1}>{r.RUN_ID}</Text>
                    <View style={{ flex: 1.5, paddingHorizontal: space(2), gap: 5, minWidth: 0 }}>
                      <Text style={{ fontSize: 12.5, color: colors.text }} numberOfLines={1}>{cur ? `${cur.n}. ${cur.title}` : '—'}</Text>
                      <StageProgress r={r} />
                    </View>
                    <View style={{ width: 190, paddingHorizontal: space(2), gap: 3 }}>
                      <Badge text={rv.label} color={rv.color} dot />
                      {skipped ? <Text style={{ fontSize: 11, color: colors.muted }}>{`${skipped} stage${skipped === 1 ? '' : 's'} skipped`}</Text> : null}
                    </View>
                    <Text style={{ width: 90, paddingHorizontal: space(2), fontSize: 12.5, color: colors.text }}>{elapsed(r.STARTED_AT, r.FINISHED_AT) || '—'}</Text>
                    <Text style={{ width: 130, paddingHorizontal: space(2), fontSize: 12.5, color: colors.text }}>{when(r.STARTED_AT)}</Text>
                    <Text style={{ width: 130, paddingHorizontal: space(2), fontSize: 12.5, color: r.FINISHED_AT ? colors.text : colors.faint }}>{r.FINISHED_AT ? when(r.FINISHED_AT) : r.STATUS === 'RUNNING' ? 'Running' : '—'}</Text>
                    <View style={{ width: 70, paddingHorizontal: space(2), alignItems: 'flex-end' }}><Feather name="arrow-right" size={15} color={colors.accent} /></View>
                  </Pressable>
                );
              })}
            </View>
          </ScrollView>
        )}
      </Panel>

      {/* E. recent activity */}
      <Panel title="Recent activity" subtitle={canAudit ? 'From the audit trail and pipeline runs' : 'Pipeline runs (the audit trail is visible to Admin, Reviewer and Ericsson)'} icon="clock">
        {!runs.data && !audit.data ? <Loading rows={4} /> : activity.length === 0 ? <EmptyState icon="clock" title="No activity yet" /> : (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', columnGap: space(6) }}>
            {[activity.slice(0, Math.ceil(activity.length / 2)), activity.slice(Math.ceil(activity.length / 2))].map((col, c) => (
              <View key={c} style={{ flexGrow: 1, flexBasis: 380, minWidth: 0 }}>
                {col.map((e, i) => (
                  <View key={`${c}-${i}`} style={{ flexDirection: 'row', gap: space(3), paddingVertical: space(2.5), borderTopWidth: i ? 1 : 0, borderTopColor: colors.border }}>
                    <View style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }}>
                      <Feather name={e.icon} size={13} color={colors.muted} />
                    </View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={{ fontSize: 13, color: colors.text }} numberOfLines={1}>{e.text}</Text>
                      <Text style={{ fontSize: 11.5, color: colors.faint, marginTop: 1 }} numberOfLines={1}>{[e.site, e.who, when(e.t)].filter(Boolean).join('  ·  ')}</Text>
                    </View>
                  </View>
                ))}
              </View>
            ))}
          </View>
        )}
      </Panel>
    </ScrollView>
  );
}
