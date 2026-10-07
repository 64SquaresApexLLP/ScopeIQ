import React from 'react';
import { View } from 'react-native';
import { label, money, num } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { space } from '../theme';
import { Card, ErrorView, KV, Loading, Muted, Row, Section, Stat, Title } from '../ui';

export function Estimate({ siteId }: { siteId: string }) {
  const d = useApi<{ estimate: R | null; drivers: R[]; requirements: R | null; services_total: number }>(`/sites/${siteId}/estimate`);
  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading />;
  const e = d.data.estimate;
  return (
    <View>
      <Muted>Illustrative rates from the reference rate card; replace with contracted rates before use.</Muted>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(2), marginTop: space(2) }}>
        <Stat label="Cycle days" value={num(e?.CYCLE_DAYS)} />
        <Stat label="Services" value={money(e?.SERVICES_USD)} />
        <Stat label="Material" value={money(e?.MATERIAL_USD)} />
        <Stat label="Total" value={money(e?.TOTAL_USD)} />
      </View>
      {d.data.requirements ? (
        <Section title="Access and rigging">
          <Card>
            <KV k="Rule" v={d.data.requirements.RULE_ID} />
            <KV k="Access" v={label(d.data.requirements.ACCESS_METHOD)} />
            <KV k="Crane days" v={num(d.data.requirements.CRANE_DAYS)} />
            <KV k="Manlift days" v={num(d.data.requirements.MANLIFT_DAYS)} />
            <KV k="Rigging" v={d.data.requirements.RIGGING_CLASS} />
          </Card>
        </Section>
      ) : null}
      <Section title={`Service drivers (${d.data.drivers.length})`}>
        {d.data.drivers.map((x) => (
          <Card key={x.LINE_ID}>
            <Row style={{ justifyContent: 'space-between' }}><Title>{x.DRIVER_CODE}</Title><Title>{money(x.AMOUNT)}</Title></Row>
            <Muted>{`${x.DESCRIPTION} - ${num(x.QTY)} ${x.UOM} x ${money(x.UNIT_RATE)}${x.SECTOR && x.SECTOR !== 'SITE' ? ` - sector ${x.SECTOR}` : ''}`}</Muted>
            <Muted numberOfLines={2}>{x.BASIS}</Muted>
          </Card>
        ))}
      </Section>
    </View>
  );
}
