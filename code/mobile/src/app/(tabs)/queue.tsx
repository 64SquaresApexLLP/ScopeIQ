// Work queue per persona: what is waiting on this role right now.
//   Scoper: open discrepancies.  Reviewer: BOM revisions in review + confirmed findings.  CX SP: BOMs in SP review.
//   Ericsson: open RFIs + SP-agreed BOMs awaiting FBA.  A&E: redlines sent.
import { router } from 'expo-router';
import React, { useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';
import { colors, space } from '../../components/theme';
import { Badge, Card, EmptyState, ErrorView, ListItem, Loading, PageHeader, s, Tabs } from '../../components/ui';
import { useAuth } from '../../lib/auth';
import { label } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';

type Q = 'disc' | 'bom' | 'rfi' | 'redline' | 'ehs';
const DEFAULTS: Record<string, { q: Q; disc: string; bom: string }> = {
  SCOPER: { q: 'disc', disc: 'OPEN', bom: 'DRAFT' },
  REVIEWER: { q: 'bom', disc: 'CONFIRMED', bom: 'IN_REVIEW' },
  CX_SP: { q: 'bom', disc: 'OPEN', bom: 'SP_REVIEW' },
  ADMIN: { q: 'rfi', disc: 'RFI_RAISED', bom: 'SP_AGREED' },
  ERICSSON: { q: 'rfi', disc: 'RFI_RAISED', bom: 'SP_AGREED' },
  AE_ENGINEER: { q: 'redline', disc: 'REDLINED', bom: 'DRAFT' },
  EHS: { q: 'ehs', disc: 'OPEN', bom: 'DRAFT' },
};

const Site = ({ id, extra }: { id: string; extra?: string }) => (
  <Text style={{ fontSize: 13.5, fontWeight: '600', color: colors.text }}>{id}{extra ? <Text style={{ color: colors.muted, fontWeight: '400' }}>{`  ·  ${extra}`}</Text> : null}</Text>
);

export default function Queue() {
  const { user } = useAuth();
  const d = DEFAULTS[user?.role ?? ''] ?? DEFAULTS.SCOPER;
  const [q, setQ] = useState<Q>(d.q);
  const path = q === 'disc' ? `/discrepancies?status=${d.disc}` : q === 'bom' ? `/bom/revisions?status=${d.bom}` : q === 'rfi' ? '/rfis' : q === 'ehs' ? '/ehs-alerts' : '/redlines';
  const data = useApi<R[]>(path);
  const rows = (data.data ?? []).filter((x) => (q === 'rfi' ? !['ANSWERED', 'CLOSED'].includes(x.STATUS) : q === 'ehs' ? x.STATUS !== 'MITIGATED' : q === 'redline' ? !['COMPLETED', 'INCORPORATED', 'CLOSED', 'REJECTED'].includes(x.STATUS) : true));
  const tabs: { key: Q; label: string }[] = user?.role === 'AE_ENGINEER'
    ? [{ key: 'redline', label: 'Redlines to complete' }, { key: 'rfi', label: 'RFIs pending an answer' }]
    : [{ key: 'disc', label: `Findings (${label(d.disc).toLowerCase()})` }, { key: 'bom', label: `BOMs (${label(d.bom).toLowerCase()})` },
      { key: 'rfi', label: 'RFIs' }, { key: 'redline', label: 'Redlines' }, { key: 'ehs', label: 'EH&S alerts' }];

  return (
    <ScrollView style={s.screen} contentContainerStyle={[s.content, { maxWidth: 1100, width: '100%', alignSelf: 'center' }]} refreshControl={<RefreshControl refreshing={data.loading} onRefresh={data.reload} />}>
      <PageHeader title={user?.role === 'CX_SP' ? 'Handshake' : 'Work queue'} subtitle="Items waiting on your role right now. Open one to review it and take action." />
      <Tabs<Q> value={q} onChange={setQ} style={{ marginBottom: space(4) }} tabs={tabs.map((t) => ({ ...t, count: t.key === q && data.data ? rows.length : undefined }))} />
      {data.error ? <ErrorView error={data.error} onRetry={data.reload} /> : null}
      {data.loading && !data.data ? <Loading rows={5} /> : (
        <Card padded={false} style={{ overflow: 'hidden' }}>
          {!rows.length ? <EmptyState icon="check-circle" title="Nothing waiting here" text="When an item needs your role it appears in this list." /> : rows.map((x, i) => {
            const last = i === rows.length - 1;
            if (q === 'disc') return (
              <ListItem key={x.DISC_ID ?? i} last={last} icon="alert-triangle" iconColor={x.SEVERITY === 'HIGH' || x.SEVERITY === 'CRITICAL' ? colors.danger : colors.warn}
                onPress={() => router.push({ pathname: '/discrepancy/[id]', params: { id: x.DISC_ID } })}
                title={<Site id={x.SITE_ID} extra={x.RULE_ID} />} subtitle={x.TITLE}
                meta={<View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginTop: 2 }}><Badge text={x.STATUS} /><Badge text={x.OUTCOME} color={colors.neutral} />{x.SECTOR ? <Badge text={`Sector ${x.SECTOR}`} color={colors.neutral} /> : null}</View>}
                right={<Badge text={x.SEVERITY} dot />} />);
            if (q === 'bom') return (
              <ListItem key={x.BOM_REV_ID ?? i} last={last} icon="list" iconColor={colors.ok} onPress={() => router.push({ pathname: '/bom/[revId]', params: { revId: x.BOM_REV_ID } })}
                title={<Site id={x.SITE_ID} extra={x.REV_LABEL} />} subtitle={`${label(x.KIND)}  ·  created ${String(x.CREATED_AT ?? '').slice(0, 10)}`} right={<Badge text={x.STATUS} dot />} />);
            if (q === 'rfi') return (
              <ListItem key={x.RFI_ID ?? i} last={last} icon="help-circle" iconColor={colors.info} onPress={() => router.push({ pathname: '/site/[id]', params: { id: x.SITE_ID, tab: 'redlines' } })}
                title={<Site id={x.SITE_ID} extra={x.TO_PARTY === 'AE_ENGINEER' ? 'To A&E Engineer' : 'To Admin'} />} subtitle={x.SUBJECT} right={<Badge text={x.STATUS} dot />} />);
            if (q === 'ehs') return (
              <ListItem key={x.ALERT_ID ?? i} last={last} icon="shield" iconColor={colors.danger} onPress={() => router.push({ pathname: '/site/[id]', params: { id: x.SITE_ID } })}
                title={<Site id={x.SITE_ID} extra={x.RULE_ID} />} subtitle={x.ALERT_TEXT} right={<><Badge text={x.SEVERITY} dot /><Badge text={x.STATUS} /></>} />);
            return (
              <ListItem key={x.REDLINE_ID ?? i} last={last} icon="edit-3" iconColor={colors.warn} onPress={() => router.push({ pathname: '/site/[id]', params: { id: x.SITE_ID, tab: 'redlines' } })}
                title={<Site id={x.SITE_ID} extra={`${x.DOC_TYPE} · sheet ${x.SHEET}`} />} subtitle={x.MARKUP}
                right={<Badge text={x.STATUS === 'WORK_QUEUE' ? 'Work queue' : x.STATUS === 'IN_REVIEW' ? 'In review' : x.STATUS} color={x.STATUS === 'WORK_QUEUE' ? colors.info : colors.warn} dot />} />);
          })}
        </Card>
      )}
    </ScrollView>
  );
}
