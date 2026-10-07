import React, { useState } from 'react';
import { RefreshControl, ScrollView, TextInput } from 'react-native';
import { colors } from '../components/theme';
import { Badge, Card, Empty, ErrorView, Muted, Row, s, Title } from '../components/ui';
import { show, when } from '../lib/format';
import { Row as R } from '../lib/types';
import { useApi } from '../lib/useApi';

export default function Audit() {
  const [site, setSite] = useState('');
  const d = useApi<R[]>(`/audit?limit=300${site.length >= 8 ? `&site_id=${site.toUpperCase()}` : ''}`);
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={d.loading} onRefresh={d.reload} />}>
      <TextInput style={s.input} placeholder="Filter by site id (e.g. TXDA1024)" value={site} onChangeText={setSite} autoCapitalize="characters" />
      {d.error ? <ErrorView error={d.error} onRetry={d.reload} /> : null}
      {!d.loading && !d.data?.length ? <Empty text="No audit entries." /> : null}
      {(d.data ?? []).map((a) => (
        <Card key={a.AUDIT_ID}>
          <Row style={{ justifyContent: 'space-between' }}><Title>{`${a.ACTION} ${a.ENTITY_TYPE}`}</Title><Badge text={a.ACTOR_ROLE} color={colors.primary} /></Row>
          <Muted>{`${when(a.EVENT_TS)} - ${a.ACTOR_USER_ID}${a.SITE_ID ? ` - ${a.SITE_ID}` : ''} - ${a.ENTITY_ID}`}</Muted>
          {a.REASON_CODE ? <Muted>{`Reason ${a.REASON_CODE}${a.COMMENT ? `: ${a.COMMENT}` : ''}`}</Muted> : a.COMMENT ? <Muted>{a.COMMENT}</Muted> : null}
          {a.BEFORE_VALUE || a.AFTER_VALUE ? <Muted numberOfLines={3}>{`${show(a.BEFORE_VALUE)} -> ${show(a.AFTER_VALUE)}`}</Muted> : null}
        </Card>
      ))}
    </ScrollView>
  );
}
