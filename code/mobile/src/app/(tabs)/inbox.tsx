// Inbox: notifications for the signed-in role. Opening one marks it read and goes to the item it is about.
import { router } from 'expo-router';
import React, { useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';
import { colors, space } from '../../components/theme';
import { Badge, Button, Card, Chips, EmptyState, ErrorView, IconName, ListItem, Loading, PageHeader, s } from '../../components/ui';
import { api } from '../../lib/api';
import { label, when } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';

function kindOf(n: R): { text: string; color: string; icon: IconName } {
  if (n.ENTITY_TYPE === 'PIPELINE_RUN') {
    const failed = n.MESSAGE?.includes('FAILED');
    return { text: failed ? 'Pipeline failed' : 'Pipeline finished', color: failed ? colors.danger : n.MESSAGE?.includes('WITH_WARNINGS') ? colors.warn : colors.ok, icon: failed ? 'alert-octagon' : 'check-circle' };
  }
  if (n.ENTITY_TYPE === 'RFI') return { text: 'RFI', color: colors.info, icon: 'help-circle' };
  if (n.ENTITY_TYPE === 'REDLINE') return { text: 'Redline', color: colors.warn, icon: 'edit-3' };
  if (n.ENTITY_TYPE === 'DISCREPANCY') return { text: 'Finding', color: colors.danger, icon: 'alert-triangle' };
  if (n.ENTITY_TYPE === 'BOM_REVISION') return { text: 'BOM revision', color: colors.ok, icon: 'list' };
  return { text: label(n.ENTITY_TYPE ?? 'Notice'), color: colors.neutral, icon: 'bell' };
}

export default function Inbox() {
  const [unread, setUnread] = useState<'unread' | 'all'>('unread');
  const inbox = useApi<R[]>(`/workflow/inbox?unread_only=${unread === 'unread'}`);
  const open = async (n: R) => {
    if (!n.READ_AT) await api.post(`/workflow/inbox/${n.NOTIFICATION_ID}/read`).catch(() => undefined);
    if (n.ENTITY_TYPE === 'DISCREPANCY') router.push({ pathname: '/discrepancy/[id]', params: { id: n.ENTITY_ID } });
    else if (n.ENTITY_TYPE === 'BOM_REVISION') router.push({ pathname: '/bom/[revId]', params: { revId: n.ENTITY_ID } });
    else if (n.SITE_ID && (n.ENTITY_TYPE === 'RFI' || n.ENTITY_TYPE === 'REDLINE')) {
      router.push({ pathname: '/site/[id]', params: { id: n.SITE_ID, tab: 'redlines' } });
    }
    else if (n.ENTITY_TYPE === 'RFI') router.push('/rfis');
    else if (n.SITE_ID) router.push({ pathname: '/site/[id]', params: { id: n.SITE_ID } });
    void inbox.reload();
  };
  const markAll = async () => {
    await Promise.all((inbox.data ?? []).filter((n) => !n.READ_AT).map((n) => api.post(`/workflow/inbox/${n.NOTIFICATION_ID}/read`)));
    void inbox.reload();
  };
  const list = inbox.data ?? [];
  return (
    <ScrollView style={s.screen} contentContainerStyle={[s.content, { maxWidth: 1100, width: '100%', alignSelf: 'center' }]} refreshControl={<RefreshControl refreshing={inbox.loading} onRefresh={inbox.reload} />}>
      <PageHeader title="Inbox" subtitle="Notifications for your role: pipeline results, findings, redlines and RFIs."
        actions={unread === 'unread' && list.length ? <Button small kind="secondary" icon="check" title="Mark all as read" onPress={markAll} /> : undefined} />
      <View style={{ marginBottom: space(3) }}>
        <Chips value={unread} onChange={setUnread} options={[{ key: 'unread', label: 'Unread', count: unread === 'unread' ? list.length : undefined }, { key: 'all', label: 'All' }]} />
      </View>
      {inbox.error ? <ErrorView error={inbox.error} onRetry={inbox.reload} /> : null}
      {inbox.loading && !inbox.data ? <Loading rows={5} /> : (
        <Card padded={false} style={{ overflow: 'hidden' }}>
          {!list.length ? <EmptyState icon="inbox" title={unread === 'unread' ? 'You are all caught up' : 'No notifications'} text="New notifications for your role appear here." /> : list.map((n, i) => {
            const k = kindOf(n);
            return (
              <ListItem key={n.NOTIFICATION_ID} icon={k.icon} iconColor={k.color} dim={!!n.READ_AT} last={i === list.length - 1} onPress={() => open(n)}
                title={<View style={{ flexDirection: 'row', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Badge text={k.text} color={k.color} />
                  {n.SITE_ID ? <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.accent }}>{n.SITE_ID}</Text> : null}
                  {!n.READ_AT ? <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: colors.accent }} /> : null}
                </View>}
                subtitle={n.MESSAGE} meta={when(n.CREATED_AT)} />
            );
          })}
        </Card>
      )}
    </ScrollView>
  );
}
