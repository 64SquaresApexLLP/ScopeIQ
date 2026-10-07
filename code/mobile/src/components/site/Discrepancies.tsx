import { router } from 'expo-router';
import React, { useState } from 'react';
import { View } from 'react-native';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, space } from '../theme';
import { Badge, Card, Chips, Empty, ErrorView, Loading, Muted, Row, Title } from '../ui';

type F = 'open' | 'all' | 'high';
export function Discrepancies({ siteId }: { siteId: string }) {
  const [f, setF] = useState<F>('open');
  const d = useApi<R[]>(`/discrepancies?site_id=${siteId}`);
  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading />;
  const rows = d.data.filter((x) => (f === 'open' ? !['RESOLVED', 'CLOSED', 'DISMISSED'].includes(x.STATUS) : f === 'high' ? x.SEVERITY === 'HIGH' : true));
  return (
    <View>
      <Chips<F> value={f} onChange={setF} options={[{ key: 'open', label: 'Unresolved' }, { key: 'high', label: 'High severity' }, { key: 'all', label: `All (${d.data.length})` }]} />
      {!rows.length ? <Empty text="No discrepancies in this view." /> : null}
      {rows.map((x) => (
        <Card key={x.DISC_ID} onPress={() => router.push({ pathname: '/discrepancy/[id]', params: { id: x.DISC_ID } })}>
          <Row style={{ justifyContent: 'space-between' }}><Title>{x.RULE_ID}</Title><Row><Badge text={x.SEVERITY} /><Badge text={x.STATUS} /></Row></Row>
          <Muted numberOfLines={2} style={{ color: colors.text }}>{x.TITLE}</Muted>
          <Row style={{ marginTop: space(1) }}>
            <Badge text={x.OUTCOME} color={colors.primary} />
            {x.SECTOR ? <Badge text={`Sector ${x.SECTOR}${x.POSITION ? ` pos ${x.POSITION}` : ''}`} color={colors.muted} /> : null}
            {x.GOVERNING ? <Muted>{`governs: ${x.GOVERNING}`}</Muted> : null}
          </Row>
        </Card>
      ))}
    </View>
  );
}
