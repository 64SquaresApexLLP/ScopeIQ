import React, { useState } from 'react';
import { View } from 'react-native';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { Chips, Empty, ErrorView, Loading } from '../ui';
import { FindingCard } from './FindingView';

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
      {rows.map((x) => <FindingCard key={x.DISC_ID} x={x} />)}
    </View>
  );
}
