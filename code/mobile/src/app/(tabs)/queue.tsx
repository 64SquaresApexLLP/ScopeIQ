// Work queue per persona: what is waiting on this role right now.
//   Scoper: open discrepancies.  Reviewer: BOM revisions in review + confirmed findings.  CX SP: BOMs in SP review.
//   Ericsson: open RFIs + SP-agreed BOMs awaiting FBA.  A&E: redlines sent.
import { router } from 'expo-router';
import React, { useState } from 'react';
import { RefreshControl, ScrollView } from 'react-native';
import { colors, space } from '../../components/theme';
import { Badge, Card, Chips, Empty, ErrorView, Loading, Muted, Row, s, Title } from '../../components/ui';
import { useAuth } from '../../lib/auth';
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

export default function Queue() {
  const { user } = useAuth();
  const d = DEFAULTS[user?.role ?? ''] ?? DEFAULTS.SCOPER;
  const [q, setQ] = useState<Q>(d.q);
  const path = q === 'disc' ? `/discrepancies?status=${d.disc}` : q === 'bom' ? `/bom/revisions?status=${d.bom}` : q === 'rfi' ? '/rfis' : q === 'ehs' ? '/ehs-alerts' : '/redlines';
  const data = useApi<R[]>(path);
  const rows = (data.data ?? []).filter((x) => (q === 'rfi' ? !['ANSWERED', 'CLOSED'].includes(x.STATUS) : q === 'ehs' ? x.STATUS !== 'MITIGATED' : q === 'redline' ? !['COMPLETED', 'INCORPORATED', 'CLOSED', 'REJECTED'].includes(x.STATUS) : true));
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={data.loading} onRefresh={data.reload} />}>
      <Chips<Q>
        value={q}
        onChange={setQ}
        options={
          user?.role === 'AE_ENGINEER'
            ? [
                { key: 'redline', label: 'Redlines (work queue)' },
                { key: 'rfi', label: 'RFIs (pending answer)' },
              ]
            : [
                { key: 'disc', label: `Discrepancies (${d.disc.replace('_', ' ').toLowerCase()})` },
                { key: 'bom', label: `BOMs (${d.bom.replace('_', ' ').toLowerCase()})` },
                { key: 'rfi', label: 'RFIs' },
                { key: 'redline', label: 'Redlines' },
                { key: 'ehs', label: 'EH&S alerts' },
              ]
        }
      />
      {data.error ? <ErrorView error={data.error} onRetry={data.reload} /> : data.loading && !data.data ? <Loading /> : null}
      {!data.loading && !rows.length ? <Empty text="Nothing waiting here." /> : null}
      {rows.map((x, i) => {
        if (q === 'disc') return (
          <Card key={x.DISC_ID ?? i} onPress={() => router.push({ pathname: '/discrepancy/[id]', params: { id: x.DISC_ID } })}>
            <Row style={{ justifyContent: 'space-between' }}><Title>{`${x.SITE_ID} - ${x.RULE_ID}`}</Title><Badge text={x.SEVERITY} /></Row>
            <Muted numberOfLines={2}>{x.TITLE}</Muted>
            <Row style={{ marginTop: space(1) }}><Badge text={x.STATUS} /><Badge text={x.OUTCOME} color={colors.primary} />{x.SECTOR ? <Badge text={`Sector ${x.SECTOR}`} color={colors.muted} /> : null}</Row>
          </Card>);
        if (q === 'bom') return (
          <Card key={x.BOM_REV_ID ?? i} onPress={() => router.push({ pathname: '/bom/[revId]', params: { revId: x.BOM_REV_ID } })}>
            <Row style={{ justifyContent: 'space-between' }}><Title>{`${x.SITE_ID} ${x.REV_LABEL}`}</Title><Badge text={x.STATUS} /></Row>
            <Muted>{`${x.KIND} - created ${String(x.CREATED_AT ?? '').slice(0, 10)}`}</Muted>
          </Card>);
        if (q === 'rfi') return (
          <Card key={x.RFI_ID ?? i} onPress={() => router.push({ pathname: '/site/[id]', params: { id: x.SITE_ID, tab: 'redlines' } })}>
            <Row style={{ justifyContent: 'space-between' }}><Title>{x.SITE_ID}</Title><Badge text={x.STATUS} /></Row>
            <Muted>{`To ${x.TO_PARTY === 'AE_ENGINEER' ? 'AE_ENGINEER' : 'Admin'}: ${x.SUBJECT}`}</Muted>
          </Card>);
        if (q === 'ehs') return (
          <Card key={x.ALERT_ID ?? i} onPress={() => router.push({ pathname: '/site/[id]', params: { id: x.SITE_ID } })}>
            <Row style={{ justifyContent: 'space-between' }}><Title>{`${x.SITE_ID} ${x.RULE_ID}`}</Title><Row><Badge text={x.SEVERITY} /><Badge text={x.STATUS} /></Row></Row>
            <Muted>{x.ALERT_TEXT}</Muted>
          </Card>);
        const displaySt = x.STATUS === 'WORK_QUEUE' ? 'WORK QUEUE' : x.STATUS === 'IN_REVIEW' ? 'IN REVIEW' : x.STATUS;
        const col = x.STATUS === 'WORK_QUEUE' ? colors.primary : colors.warn;
        return (
          <Card key={x.REDLINE_ID ?? i} onPress={() => router.push({ pathname: '/site/[id]', params: { id: x.SITE_ID, tab: 'redlines' } })}>
            <Row style={{ justifyContent: 'space-between' }}>
              <Title>{`${x.SITE_ID} ${x.DOC_TYPE} ${x.SHEET}`}</Title>
              <Badge text={displaySt} color={col} />
            </Row>
            <Muted numberOfLines={2}>{x.MARKUP}</Muted>
          </Card>);
      })}
    </ScrollView>
  );
}
