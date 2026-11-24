// Sites: searchable, filterable list of the sites the signed-in persona can see, with documents and pipeline status.
import { router, useFocusEffect } from 'expo-router';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import { RefreshControl, ScrollView, Text, View, useWindowDimensions } from 'react-native';
import { colors, space } from '../../components/theme';
import { Badge, Button, Card, Chips, Column, ConfirmDialog, DataTable, EmptyState, ErrorView, Icon, IconButton, Loading, PageHeader, s, SearchBox, Select } from '../../components/ui';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { label, when } from '../../lib/format';
import { PipelineRun, PipelineStep, Row as R } from '../../lib/types';
import { mutateApi, useApi } from '../../lib/useApi';
import { ProviderHome } from '../../components/ProviderHome';

type RunState = 'NONE' | 'RUNNING' | 'DONE' | 'WARN' | 'STOPPED' | 'FAILED';
const RUN_STATE: Record<RunState, { text: string; color: string }> = {
  NONE: { text: 'Not run', color: colors.neutral }, RUNNING: { text: 'Running', color: colors.info }, DONE: { text: 'Completed', color: colors.ok },
  WARN: { text: 'Done, with warnings', color: colors.warn }, STOPPED: { text: 'Stopped at stage 4', color: colors.warn }, FAILED: { text: 'Failed', color: colors.danger },
};
const FILTERS: { key: 'ALL' | RunState; label: string }[] = [
  { key: 'ALL', label: 'All' }, { key: 'NONE', label: 'Not run' }, { key: 'RUNNING', label: 'Running' }, { key: 'DONE', label: 'Completed' },
  { key: 'STOPPED', label: 'Stopped' }, { key: 'FAILED', label: 'Failed' },
];

function runState(r?: PipelineRun): RunState {
  if (!r) return 'NONE';
  const steps = Array.isArray(r.STEPS) ? (r.STEPS as PipelineStep[]) : [];
  if (r.STATUS === 'RUNNING') return 'RUNNING';
  if (r.STATUS === 'FAILED' || steps.some((x) => x.status === 'FAILED')) return 'FAILED';
  if (steps.some((x) => x.status === 'SKIPPED')) return 'STOPPED';
  return r.STATUS === 'SUCCEEDED_WITH_WARNINGS' ? 'WARN' : 'DONE';
}
const stageText = (r?: PipelineRun) => {
  const steps = r && Array.isArray(r.STEPS) ? (r.STEPS as PipelineStep[]) : [];
  if (!steps.length) return '';
  const failed = steps.findIndex((x) => x.status === 'FAILED');
  if (failed >= 0) return `Stage ${failed + 1}: ${steps[failed].label}`;
  return `${steps.filter((x) => x.status === 'DONE').length} of ${steps.length} stages`;
};

function Docs({ item }: { item: R }) {
  const byType: Record<string, number> = item.DOC_BY_TYPE ?? {};
  const n: number = item.DOC_COUNT ?? 0;
  const sp: number = item.SHAREPOINT_FILES ?? 0;
  if (n) {
    return (
      <View style={{ gap: 4 }}>
        <Text style={{ fontSize: 13, color: colors.text, fontWeight: '500' }}>{n} registered</Text>
        <Text style={{ fontSize: 11.5, color: colors.muted }} numberOfLines={1}>{Object.keys(byType).map((t) => t.replace(/_/g, ' ')).join(', ')}</Text>
      </View>
    );
  }
  if (item.PIPELINE_NEEDED) return <View style={{ gap: 4 }}><Text style={{ fontSize: 13, color: colors.text }}>{sp} uploaded</Text><Text style={{ fontSize: 11.5, color: colors.warn }}>Not processed yet</Text></View>;
  return <Text style={{ fontSize: 13, color: colors.faint }}>No documents</Text>;
}

export default function SitesPage() {
  const { user } = useAuth();
  return user?.role === 'CX_SP' ? <ProviderHome /> : <Sites />;
}

function Sites() {
  const { user, can } = useAuth();
  const { width } = useWindowDimensions();
  const sites = useApi<R[]>('/sites');
  const runs = useApi<PipelineRun[]>('/pipeline/runs?limit=500');
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState<'ALL' | RunState>('ALL');
  const [state, setState] = useState<string>('ALL');
  const [toDelete, setToDelete] = useState<string | null>(null);
  const [deleteErr, setDeleteErr] = useState<Error | null>(null);
  const isAe = user?.role === 'AE_ENGINEER';

  const firstFocus = useRef(true);
  useFocusEffect(useCallback(() => {
    if (firstFocus.current) { firstFocus.current = false; return; }
    void sites.reload(true); void runs.reload(true);
  }, [sites.reload, runs.reload]));

  const latest = useMemo(() => {
    const m = new Map<string, PipelineRun>();
    for (const r of runs.data ?? []) if (r.RUN_ID?.startsWith('RUN-') && !m.has(r.SITE_ID)) m.set(r.SITE_ID, r);
    return m;
  }, [runs.data]);

  const all = sites.data ?? [];
  const states = useMemo(() => [...new Set(all.map((x) => x.WORKFLOW_STATE).filter(Boolean))].sort() as string[], [all]);
  const counts = useMemo(() => {
    const c: Record<string, number> = { ALL: all.length };
    for (const x of all) { const k = runState(latest.get(x.SITE_ID)); c[k] = (c[k] ?? 0) + 1; if (k === 'WARN') c.DONE = (c.DONE ?? 0) + 1; }
    return c;
  }, [all, latest]);
  const rows = useMemo(() => all.filter((x) => {
    const rs = runState(latest.get(x.SITE_ID));
    if (filter !== 'ALL' && !(rs === filter || (filter === 'DONE' && rs === 'WARN'))) return false;
    if (state !== 'ALL' && x.WORKFLOW_STATE !== state) return false;
    return !q || JSON.stringify([x.SITE_ID, x.SITE_NAME, x.CITY, x.STATE, x.CX_SP]).toLowerCase().includes(q.toLowerCase());
  }), [all, latest, filter, state, q]);

  const open = (sid: string) => router.push({ pathname: '/site/[id]', params: isAe ? { id: sid, tab: 'redlines' } : { id: sid } });
  const doDelete = async () => {
    const sid = toDelete;
    setToDelete(null);
    if (!sid) return;
    try {
      await api.del(`/sites/${encodeURIComponent(sid)}`);
      void sites.reload();
      mutateApi('/sites'); mutateApi('/sharepoint/sites'); mutateApi('/sites/dashboard');
    } catch (e: any) {
      setDeleteErr(new Error(`Could not delete site ${sid}: ${e?.message || e}`));
    }
  };

  const columns: Column<R>[] = [
    { key: 'site', title: 'Site', flex: 1.3, render: (x) => (
      <View style={{ gap: 2 }}>
        <Text style={{ fontSize: 13.5, fontWeight: '600', color: colors.text }}>{x.SITE_ID}</Text>
        <Text style={{ fontSize: 12, color: colors.muted }} numberOfLines={1}>{x.SITE_NAME || '—'}</Text>
      </View>) },
    { key: 'loc', title: 'Location', flex: 1, render: (x) => <Text style={{ fontSize: 13, color: x.CITY ? colors.text : colors.faint }} numberOfLines={1}>{[x.CITY, x.STATE].filter(Boolean).join(', ') || 'Not set'}</Text> },
    { key: 'stream', title: 'Stream', width: 128, render: (x) => <View style={{ gap: 4 }}>{x.STREAM ? <Badge text={x.STREAM} color={colors.neutral} /> : <Text style={{ color: colors.faint }}>—</Text>}{x.STRUCTURE_TYPE ? <Text style={{ fontSize: 11.5, color: colors.muted }} numberOfLines={1}>{x.STRUCTURE_TYPE}</Text> : null}</View> },
    { key: 'docs', title: 'Documents', flex: 1.2, render: (x) => <Docs item={x} /> },
    { key: 'pipe', title: 'Pipeline', flex: 1.5, render: (x) => {
      const r = latest.get(x.SITE_ID); const st = RUN_STATE[runState(r)];
      return <View style={{ gap: 4 }}><Badge text={st.text} color={st.color} dot />{r ? <Text style={{ fontSize: 11.5, color: colors.muted }} numberOfLines={1}>{stageText(r)}</Text> : null}</View>;
    } },
    { key: 'last', title: 'Last run', width: 130, render: (x) => <Text style={{ fontSize: 12.5, color: latest.get(x.SITE_ID) ? colors.text : colors.faint }}>{latest.get(x.SITE_ID) ? when(latest.get(x.SITE_ID)!.STARTED_AT) : 'Never'}</Text> },
    { key: 'open', title: 'Open findings', width: 124, align: 'right', render: (x) => <Text style={{ fontSize: 13.5, fontWeight: '600', color: x.OPEN_DISCREPANCIES ? colors.danger : colors.faint }}>{x.OPEN_DISCREPANCIES ?? 0}</Text> },
    { key: 'act', title: '', width: can('ADMIN') ? 132 : 92, align: 'right', render: (x) => (
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
        <Button small kind="secondary" title="View" onPress={() => open(x.SITE_ID)} />
        {can('ADMIN') ? <IconButton icon="trash-2" label={`Delete site ${x.SITE_ID}`} danger onPress={() => setToDelete(x.SITE_ID)} /> : null}
      </View>) },
  ];

  const narrow = width < 900;
  return (
    <ScrollView style={s.screen} contentContainerStyle={[s.content, { maxWidth: 1440, width: '100%', alignSelf: 'center' }]}
      refreshControl={<RefreshControl refreshing={sites.loading} onRefresh={() => { void sites.reload(); void runs.reload(); }} />}>
      <PageHeader title="Sites" subtitle="Cell sites in scope, their documents and the state of their latest pipeline run."
        actions={can('ADMIN') ? <Button small icon="plus" title="Create site" onPress={() => router.push('/(tabs)/admin')} /> : undefined} />

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), flexWrap: 'wrap', marginBottom: space(3), zIndex: 5 }}>
        <SearchBox value={q} onChangeText={setQ} placeholder="Search by site ID, name, city or service provider" style={{ flex: 1, minWidth: 260 }} />
        {states.length > 1 ? <Select value={state} onChange={setState} width={220} options={[{ key: 'ALL', label: 'All workflow states' }, ...states.map((k) => ({ key: k, label: label(k) }))]} /> : null}
      </View>
      <View style={{ marginBottom: space(3) }}>
        <Chips value={filter} onChange={setFilter} options={FILTERS.map((f) => ({ key: f.key, label: f.label, count: counts[f.key] ?? 0 }))} />
      </View>

      {sites.error ? <ErrorView error={sites.error} onRetry={sites.reload} /> : null}
      {deleteErr ? <ErrorView error={deleteErr} onRetry={() => setDeleteErr(null)} /> : null}
      {!sites.data ? <Loading rows={6} /> : narrow ? (
        rows.length === 0 ? <Card><EmptyState icon="map-pin" title="No sites match" text={all.length ? 'Change the search or filters.' : 'No sites are assigned to you.'} /></Card> : rows.map((x) => {
          const r = latest.get(x.SITE_ID); const st = RUN_STATE[runState(r)];
          return (
            <Card key={x.SITE_ID} onPress={() => open(x.SITE_ID)}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space(2) }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 15, fontWeight: '600', color: colors.text }}>{x.SITE_ID}</Text>
                  <Text style={s.muted} numberOfLines={1}>{[x.SITE_NAME, [x.CITY, x.STATE].filter(Boolean).join(', ')].filter(Boolean).join('  ·  ') || 'No location details'}</Text>
                </View>
                <Icon name="chevron-right" size={16} />
              </View>
              <View style={{ flexDirection: 'row', gap: space(2), marginTop: space(3), flexWrap: 'wrap', alignItems: 'center' }}>
                <Badge text={st.text} color={st.color} dot />
                {x.STREAM ? <Badge text={x.STREAM} color={colors.neutral} /> : null}
                {x.OPEN_DISCREPANCIES ? <Badge text={`${x.OPEN_DISCREPANCIES} open findings`} color={colors.danger} /> : null}
              </View>
              <View style={{ marginTop: space(3) }}><Docs item={x} /></View>
            </Card>
          );
        })
      ) : (
        <DataTable columns={columns} rows={rows} keyFor={(x) => x.SITE_ID} onRowPress={(x) => open(x.SITE_ID)} minWidth={1100}
          empty={<EmptyState icon="map-pin" title="No sites match" text={all.length ? 'Change the search or filters.' : 'No sites are assigned to you.'} />} />
      )}
      {sites.data ? <Text style={[s.muted, { fontSize: 12, marginTop: space(2) }]}>{`Showing ${rows.length} of ${all.length} site${all.length === 1 ? '' : 's'}`}</Text> : null}

      <ConfirmDialog open={!!toDelete} danger title={`Delete site ${toDelete ?? ''}?`} confirmText="Delete site"
        message="This permanently removes the site with all its documents, run history, findings and files. It cannot be undone."
        onConfirm={doDelete} onCancel={() => setToDelete(null)} />
    </ScrollView>
  );
}
