import { router } from 'expo-router';
import React, { useState } from 'react';
import { RefreshControl, ScrollView } from 'react-native';
import { colors } from '../../components/theme';
import { Badge, Button, Card, Chips, Empty, ErrorView, Muted, Row, s } from '../../components/ui';
import { api } from '../../lib/api';
import { when } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';

export default function Inbox() {
  const [unread, setUnread] = useState<'unread' | 'all'>('unread');
  const inbox = useApi<R[]>(`/workflow/inbox?unread_only=${unread === 'unread'}`);
  const open = async (n: R) => {
    if (!n.READ_AT) await api.post(`/workflow/inbox/${n.NOTIFICATION_ID}/read`).catch(() => undefined);
    if (n.ENTITY_TYPE === 'DISCREPANCY') router.push({ pathname: '/discrepancy/[id]', params: { id: n.ENTITY_ID } });
    else if (n.ENTITY_TYPE === 'BOM_REVISION') router.push({ pathname: '/bom/[revId]', params: { revId: n.ENTITY_ID } });
    else if (n.SITE_ID) router.push({ pathname: '/site/[id]', params: { id: n.SITE_ID } });
    void inbox.reload();
  };
  const markAll = async () => {
    await Promise.all((inbox.data ?? []).filter((n) => !n.READ_AT).map((n) => api.post(`/workflow/inbox/${n.NOTIFICATION_ID}/read`)));
    void inbox.reload();
  };
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={inbox.loading} onRefresh={inbox.reload} />}>
      <Row style={{ justifyContent: 'space-between' }}>
        <Chips value={unread} onChange={setUnread} options={[{ key: 'unread', label: 'Unread' }, { key: 'all', label: 'All' }]} />
        {unread === 'unread' && inbox.data?.length ? <Button small kind="secondary" title="Mark all read" onPress={markAll} /> : null}
      </Row>
      {inbox.error ? <ErrorView error={inbox.error} onRetry={inbox.reload} /> : null}
      {!inbox.loading && !inbox.data?.length ? <Empty text="No notifications for your role." /> : null}
      {(inbox.data ?? []).map((n) => (
        <Card key={n.NOTIFICATION_ID} onPress={() => open(n)} style={n.READ_AT ? { opacity: 0.6 } : undefined}>
          <Row><Badge text={n.ENTITY_TYPE} color={colors.primary} />{n.SITE_ID ? <Badge text={n.SITE_ID} color={colors.muted} /> : null}</Row>
          <Muted style={{ marginTop: 4, color: colors.text }}>{n.MESSAGE}</Muted>
          <Muted>{when(n.CREATED_AT)}</Muted>
        </Card>
      ))}
    </ScrollView>
  );
}
