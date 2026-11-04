import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, space } from '../theme';
import { Chips, Empty, ErrorView, Icon, Loading } from '../ui';
import { FindingCard } from './FindingView';

type F = 'open' | 'resolved' | 'all' | 'high';

export function Discrepancies({ siteId }: { siteId: string }) {
  const [f, setF] = useState<F>('open');
  const d = useApi<R[]>(`/discrepancies?site_id=${siteId}`);

  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading />;

  const isResolvedOrClosed = (x: R) =>
    x.AE_STATUS === 'REDLINE_REMOVED' ||
    x.STATUS === 'CLOSED' ||
    (x.STATUS === 'RESOLVED' && x.AE_STATUS !== 'IMPROVED_REV_RECEIVED' && !x.REDLINE_PENDING_REMOVAL);

  const openRows = d.data.filter((x) => !isResolvedOrClosed(x));
  const resolvedRows = d.data.filter((x) => isResolvedOrClosed(x));

  let displayRows: R[] = [];
  if (f === 'all') {
    displayRows = d.data;
  } else if (f === 'open') {
    displayRows = openRows;
  } else if (f === 'resolved') {
    displayRows = resolvedRows;
  } else if (f === 'high') {
    displayRows = d.data.filter((x) => x.SEVERITY === 'HIGH');
  }

  return (
    <View>
      <Chips<F>
        value={f}
        onChange={setF}
        options={[
          { key: 'open', label: `Unresolved (${openRows.length})` },
          { key: 'resolved', label: `Resolved (${resolvedRows.length})` },
          { key: 'all', label: `All (${d.data.length})` },
          { key: 'high', label: 'High severity' },
        ]}
      />

      {/* When in Unresolved tab: show open discrepancies, followed by Old / Resolved discrepancies */}
      {f === 'open' ? (
        <View>
          {!openRows.length && !resolvedRows.length ? (
            <Empty text="No discrepancies found for this site." />
          ) : null}

          {openRows.map((x) => (
            <FindingCard key={x.DISC_ID} x={x} onReload={d.reload} />
          ))}

          {resolvedRows.length > 0 ? (
            <View style={{ marginTop: openRows.length ? space(5) : space(2) }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), marginBottom: space(3) }}>
                <Icon name="check-circle" size={16} color="#059669" />
                <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>
                  Old Discrepancies (Resolved via Redlines) ({resolvedRows.length})
                </Text>
              </View>
              {resolvedRows.map((x) => (
                <FindingCard key={x.DISC_ID} x={x} onReload={d.reload} />
              ))}
            </View>
          ) : null}
        </View>
      ) : (
        <View>
          {!displayRows.length ? <Empty text="No discrepancies in this view." /> : null}
          {displayRows.map((x) => (
            <FindingCard key={x.DISC_ID} x={x} onReload={d.reload} />
          ))}
        </View>
      )}
    </View>
  );
}
