import { router } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { FlatList, RefreshControl, TextInput, View } from 'react-native';
import { colors, space } from '../../components/theme';
import { Badge, Card, Empty, ErrorView, Muted, Row, s, Title } from '../../components/ui';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';

export default function Sites() {
  const sites = useApi<R[]>('/sites');
  const [q, setQ] = useState('');
  const rows = useMemo(() => (sites.data ?? []).filter((x) => !q || JSON.stringify([x.SITE_ID, x.SITE_NAME, x.CITY, x.CX_SP]).toLowerCase().includes(q.toLowerCase())), [sites.data, q]);
  return (
    <View style={s.screen}>
      <View style={{ padding: space(4), paddingBottom: 0 }}>
        <TextInput style={s.input} placeholder="Search site, city or service provider" value={q} onChangeText={setQ} />
      </View>
      {sites.error ? <View style={s.content}><ErrorView error={sites.error} onRetry={sites.reload} /></View> : null}
      <FlatList
        data={rows}
        keyExtractor={(x) => x.SITE_ID}
        contentContainerStyle={s.content}
        refreshControl={<RefreshControl refreshing={sites.loading} onRefresh={sites.reload} />}
        ListEmptyComponent={sites.loading ? null : <Empty text="No sites assigned to you." />}
        renderItem={({ item }) => (
          <Card onPress={() => router.push({ pathname: '/site/[id]', params: { id: item.SITE_ID } })}>
            <Row style={{ justifyContent: 'space-between' }}>
              <Title>{item.SITE_ID}</Title>
              <Badge text={item.WORKFLOW_STATE} color={colors.primary} />
            </Row>
            <Muted>{`${item.SITE_NAME ?? ''} - ${item.CITY ?? ''}, ${item.STATE ?? ''}`}</Muted>
            <Row style={{ marginTop: space(2) }}>
              <Badge text={item.STREAM} color={colors.info} />
              <Badge text={item.STRUCTURE_TYPE} color={colors.muted} />
              {item.OPEN_DISCREPANCIES ? <Badge text={`${item.OPEN_DISCREPANCIES} open`} color={colors.danger} /> : <Badge text="no open findings" color={colors.ok} />}
            </Row>
            <Muted style={{ marginTop: space(1) }}>{`CX SP: ${item.CX_SP ?? '-'}  |  BOM ${item.CURRENT_BOM_REV ?? '-'}`}</Muted>
          </Card>
        )}
      />
    </View>
  );
}
