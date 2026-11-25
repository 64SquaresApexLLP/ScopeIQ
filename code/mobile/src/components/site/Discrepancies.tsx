// The findings of one site as a working list: where each stands (needs a decision, with A&E, corrected drawing received, RFI raised, resolved),
// filters and search, and what this role can do about them, one by one or several at once.
import { router } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { api, ApiError } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, radius, space, tint } from '../theme';
import { Badge, Button, Card, Chips, Column, DataTable, EmptyState, ErrorView, Icon, Loading, SearchBox, Select, Stat } from '../ui';
import { FAMILY, OUTCOME, sevOf, whereOf } from './FindingView';

type Stage = 'NEEDS' | 'WITH_AE' | 'RECEIVED' | 'RFI' | 'RESOLVED';
const STAGE: Record<Stage, { text: string; color: string }> = {
  NEEDS: { text: 'Needs a decision', color: colors.danger },
  WITH_AE: { text: 'With A&E', color: colors.info },
  RECEIVED: { text: 'Corrected drawing received', color: colors.ok },
  RFI: { text: 'RFI raised', color: colors.warn },
  RESOLVED: { text: 'Resolved', color: colors.neutral },
};
const SEV_RANK: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

const stageOf = (x: R): Stage => {
  if (x.AE_STATUS === 'REDLINE_REMOVED' || x.STATUS === 'CLOSED' || (x.STATUS === 'RESOLVED' && x.AE_STATUS !== 'IMPROVED_REV_RECEIVED' && !x.REDLINE_PENDING_REMOVAL)) return 'RESOLVED';
  if (x.AE_STATUS === 'IMPROVED_REV_RECEIVED') return 'RECEIVED';
  if (x.AE_STATUS === 'SENT_TO_AE') return 'WITH_AE';
  if (x.AE_STATUS === 'RFI_RAISED' || x.STATUS === 'RFI_RAISED') return 'RFI';
  return 'NEEDS';
};

export function Discrepancies({ siteId }: { siteId: string }) {
  const { user } = useAuth();
  const d = useApi<R[]>(`/discrepancies?site_id=${siteId}`);
  const [stage, setStage] = useState<Stage | 'ALL'>('NEEDS');
  const [sev, setSev] = useState<string>('ALL');
  const [family, setFamily] = useState<string>('ALL');
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const canAct = ['SCOPER', 'REVIEWER', 'ADMIN'].includes(user?.role ?? '');      // the people who confirm findings and send them on

  const rows = d.data ?? [];
  const withStage = useMemo(() => rows.map((x) => ({ x, st: stageOf(x) })), [rows]);
  const counts = useMemo(() => {
    const c: Record<string, number> = { ALL: rows.length };
    for (const { st } of withStage) c[st] = (c[st] ?? 0) + 1;
    return c;
  }, [withStage, rows.length]);
  const families = useMemo(() => [...new Set(rows.map((x) => x.FAMILY).filter(Boolean))].sort(), [rows]);
  const high = withStage.filter(({ x, st }) => st !== 'RESOLVED' && (x.SEVERITY === 'HIGH' || x.SEVERITY === 'CRITICAL')).length;

  const list = useMemo(() => {
    const t = query.trim().toLowerCase();
    return withStage
      .filter(({ x, st }) => (stage === 'ALL' || st === stage) && (sev === 'ALL' || x.SEVERITY === sev) && (family === 'ALL' || x.FAMILY === family)
        && (!t || [x.TITLE, x.RULE_ID, x.FAMILY, whereOf(x)].some((v) => String(v ?? '').toLowerCase().includes(t))))
      .sort((a, b) => (SEV_RANK[a.x.SEVERITY] ?? 9) - (SEV_RANK[b.x.SEVERITY] ?? 9) || String(a.x.TITLE).localeCompare(String(b.x.TITLE)));
  }, [withStage, stage, sev, family, query]);

  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading />;

  const sendable = list.filter(({ st }) => st === 'NEEDS').map(({ x }) => x.DISC_ID);
  const chosen = sendable.filter((id) => picked.has(id));
  const toggle = (id: string) => setPicked((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const call = async (ids: string[], path: 'send-to-ae' | 'remove-redline') => {
    setBusy(true);
    setErr(null);
    try {
      for (const id of ids) await api.post(`/discrepancies/${id}/${path}`, {});
      setPicked(new Set());
      await d.reload();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  const stop = (fn: () => void) => (e: any) => { e?.stopPropagation?.(); fn(); };

  const columns: Column<{ x: R; st: Stage }>[] = [
    ...(canAct ? [{ key: 'pick', title: '', width: 44, render: ({ x, st }: { x: R; st: Stage }) => st === 'NEEDS' ? (
      <Pressable onPress={stop(() => toggle(x.DISC_ID))} accessibilityRole="checkbox" accessibilityState={{ checked: picked.has(x.DISC_ID) }} accessibilityLabel={`Select ${x.TITLE}`}
        style={{ width: 18, height: 18, borderRadius: 4, borderWidth: 1.5, borderColor: picked.has(x.DISC_ID) ? colors.accent : colors.borderStrong, backgroundColor: picked.has(x.DISC_ID) ? colors.accent : '#fff', alignItems: 'center', justifyContent: 'center' }}>
        {picked.has(x.DISC_ID) ? <Icon name="check" size={12} color="#fff" /> : null}
      </Pressable>
    ) : null }] : []),
    { key: 'sev', title: 'Severity', width: 104, render: ({ x }) => <Badge text={sevOf(x).label} color={sevOf(x).color} dot /> },
    { key: 'finding', title: 'Finding', flex: 2.4, render: ({ x }) => (
      <View style={{ gap: 2 }}>
        <Text style={{ fontSize: 13.5, fontWeight: '600', color: colors.text }} numberOfLines={2}>{x.TITLE}</Text>
        <Text style={{ fontSize: 12, color: colors.muted }} numberOfLines={1}>{[whereOf(x), FAMILY[x.FAMILY] ?? x.FAMILY, x.RULE_ID].filter(Boolean).join('  ·  ')}</Text>
      </View>
    ) },
    { key: 'next', title: 'Next step', flex: 1.2, render: ({ x, st }) => st === 'RESOLVED' ? <Text style={{ fontSize: 12.5, color: colors.faint }}>None</Text> : (
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Icon name={(OUTCOME[x.OUTCOME]?.icon ?? 'chevron-right') as any} size={13} color={colors.accent} />
        <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.accent }} numberOfLines={1}>{OUTCOME[x.OUTCOME]?.label ?? x.OUTCOME}</Text>
      </View>
    ) },
    { key: 'stage', title: 'Where it stands', flex: 1.3, render: ({ x, st }) => (
      <View style={{ gap: 3, alignItems: 'flex-start' }}>
        <Badge text={STAGE[st].text} color={STAGE[st].color} />
        {x.AE_REVISION_LABEL && (st === 'RECEIVED' || st === 'RESOLVED') ? <Text style={{ fontSize: 11.5, color: colors.muted }}>{x.AE_REVISION_LABEL}</Text> : null}
      </View>
    ) },
    { key: 'act', title: '', width: canAct ? 150 : 40, align: 'right', render: ({ x, st }) => (
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2) }}>
        {canAct && st === 'NEEDS' ? <Button small kind="secondary" icon="send" title="Send to A&E" disabled={busy} onPress={stop(() => call([x.DISC_ID], 'send-to-ae')) as any} /> : null}
        {canAct && st === 'RECEIVED' ? <Button small kind="secondary" icon="check" title="Remove redline" disabled={busy} onPress={stop(() => call([x.DISC_ID], 'remove-redline')) as any} /> : null}
        <Icon name="chevron-right" size={16} color={colors.faint} />
      </View>
    ) },
  ];

  return (
    <View style={{ gap: space(4) }}>
      <View style={{ flexDirection: 'row', gap: space(3), flexWrap: 'wrap' }}>
        <Stat label="Findings" value={counts.ALL} icon="alert-triangle" />
        <Stat label="Need a decision" value={counts.NEEDS ?? 0} icon="help-circle" color={counts.NEEDS ? colors.danger : undefined} onPress={() => setStage('NEEDS')} />
        <Stat label="High or critical, open" value={high} icon="alert-octagon" color={high ? colors.red : undefined} onPress={() => { setStage('ALL'); setSev('HIGH'); }} />
        <Stat label="With A&E" value={counts.WITH_AE ?? 0} icon="send" color={colors.info} onPress={() => setStage('WITH_AE')} />
        <Stat label="Resolved" value={counts.RESOLVED ?? 0} icon="check-circle" color={colors.ok} onPress={() => setStage('RESOLVED')} />
      </View>

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), flexWrap: 'wrap', zIndex: 5 }}>
        <SearchBox value={query} onChangeText={setQuery} placeholder="Search finding, rule or place" style={{ flex: 1, minWidth: 240 }} />
        <Select<string> value={sev} width={170} onChange={setSev} options={[{ key: 'ALL', label: 'Any severity' }, { key: 'CRITICAL', label: 'Critical' }, { key: 'HIGH', label: 'High' }, { key: 'MEDIUM', label: 'Medium' }, { key: 'LOW', label: 'Low' }]} />
        {families.length > 1 ? <Select<string> value={family} width={190} onChange={setFamily} options={[{ key: 'ALL', label: 'All kinds' }, ...families.map((f) => ({ key: f, label: FAMILY[f] ?? f }))]} /> : null}
      </View>
      <Chips<Stage | 'ALL'> value={stage} onChange={setStage} options={[
        { key: 'NEEDS', label: 'Needs a decision', count: counts.NEEDS ?? 0 }, { key: 'WITH_AE', label: 'With A&E', count: counts.WITH_AE ?? 0 },
        { key: 'RECEIVED', label: 'Corrected drawing received', count: counts.RECEIVED ?? 0 }, { key: 'RFI', label: 'RFI raised', count: counts.RFI ?? 0 },
        { key: 'RESOLVED', label: 'Resolved', count: counts.RESOLVED ?? 0 }, { key: 'ALL', label: 'All', count: counts.ALL }]} />

      {canAct && stage === 'NEEDS' && sendable.length ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), flexWrap: 'wrap', padding: space(3), borderRadius: radius.lg, backgroundColor: tint.info.bg, borderWidth: 1, borderColor: tint.info.line }}>
          <Pressable onPress={() => setPicked(chosen.length === sendable.length ? new Set() : new Set(sendable))} accessibilityRole="button">
            <Text style={{ fontSize: 13, fontWeight: '600', color: colors.accent }}>{chosen.length === sendable.length ? 'Clear selection' : `Select all ${sendable.length}`}</Text>
          </Pressable>
          <Text style={{ flex: 1, fontSize: 12.5, color: colors.text }}>{chosen.length ? `${chosen.length} selected` : 'Tick findings to send several to the A&E engineer at once.'}</Text>
          <Button small icon="send" title={chosen.length ? `Send ${chosen.length} to A&E` : 'Send to A&E'} disabled={!chosen.length || busy} onPress={() => call(chosen, 'send-to-ae')} />
        </View>
      ) : null}
      {err ? <ErrorView error={err} /> : null}

      <DataTable columns={columns} rows={list} keyFor={({ x }) => x.DISC_ID} minWidth={880}
        onRowPress={({ x }) => router.push({ pathname: '/discrepancy/[id]', params: { id: x.DISC_ID } })}
        empty={<EmptyState icon="check-circle" title={query || sev !== 'ALL' || family !== 'ALL' ? 'No findings match' : stage === 'NEEDS' ? 'Nothing needs a decision' : 'No findings here'}
          text={query || sev !== 'ALL' || family !== 'ALL' ? 'Change the search or filters to see more.' : 'Findings appear after a pipeline run compares the site documents.'} />} />
    </View>
  );
}
