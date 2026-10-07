import React, { useState } from 'react';
import { RefreshControl, ScrollView } from 'react-native';
import { Badge, Card, Chips, Empty, ErrorView, KV, Muted, Row, s, Title } from '../components/ui';
import { show, when } from '../lib/format';
import { Row as R } from '../lib/types';
import { useApi } from '../lib/useApi';

type V = 'errors' | 'app' | 'config';
export default function Logs() {
  const [v, setV] = useState<V>('errors');
  const d = useApi<R[] | R>(v === 'errors' ? '/logs/errors?limit=100' : v === 'app' ? '/logs/app?limit=200' : '/config');
  const rows = Array.isArray(d.data) ? d.data : [];
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={d.loading} onRefresh={d.reload} />}>
      <Chips<V> value={v} onChange={setV} options={[{ key: 'errors', label: 'Errors' }, { key: 'app', label: 'Application log' }, { key: 'config', label: 'Runtime config' }]} />
      {d.error ? <ErrorView error={d.error} onRetry={d.reload} /> : null}
      {v === 'config' && d.data && !Array.isArray(d.data) ? (
        <Card>{Object.entries(d.data).map(([k, val]) => <KV key={k} k={k} v={show(val)} />)}</Card>
      ) : null}
      {v !== 'config' && !d.loading && !rows.length ? <Empty text="Nothing logged." /> : null}
      {v === 'errors' && rows.map((e) => (
        <Card key={e.ERROR_ID}>
          <Row style={{ justifyContent: 'space-between' }}><Title>{e.ERROR_CODE ?? e.EXCEPTION_TYPE}</Title><Muted>{when(e.ERROR_TS)}</Muted></Row>
          <Muted>{e.MESSAGE}</Muted>
          <Muted>{`${e.WHERE_RAISED ?? ''} - ref ${e.CORRELATION_ID ?? '-'}${e.SITE_ID ? ` - ${e.SITE_ID}` : ''}`}</Muted>
        </Card>
      ))}
      {v === 'app' && rows.map((e) => (
        <Card key={e.LOG_ID}>
          <Row><Badge text={e.LEVEL} /><Muted>{`${when(e.LOG_TS)} ${e.LOGGER}`}</Muted></Row>
          <Muted>{e.MESSAGE}</Muted>
        </Card>
      ))}
    </ScrollView>
  );
}
