import { router, useFocusEffect } from 'expo-router';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import { FlatList, RefreshControl, Text, TextInput, View } from 'react-native';
import { colors, space } from '../../components/theme';
import { Badge, Card, Empty, ErrorView, Icon, Muted, Row, s, Title } from '../../components/ui';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';

// Colour per document category so each pill is distinct
const DOC_TYPE_COLORS: Record<string, string> = {
  RFDS: '#7C3AED',
  CD: '#0369A1',
  MA_SA: '#0F766E',
  BOM_REV0: '#B45309',
  DRONE_META: '#6D28D9',
  DRONE_IMAGE: '#9333EA',
  DRONE_VIDEO: '#A21CAF',
  DRONE_POINTCLOUD: '#0891B2',
  DRONE_VENDOR: '#7E22CE',
};
const docColor = (t: string) => DOC_TYPE_COLORS[t] ?? colors.info;

export default function Sites() {
  const sites = useApi<R[]>('/sites');
  const [q, setQ] = useState('');

  // Automatically refresh when navigating back to Sites tab (e.g. after admin creates a site)
  const firstFocus = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (firstFocus.current) {
        firstFocus.current = false;
        return;
      }
      sites.reload(true);
    }, [sites.reload]),
  );

  const rows = useMemo(
    () =>
      (sites.data ?? []).filter(
        (x) =>
          !q ||
          JSON.stringify([x.SITE_ID, x.SITE_NAME, x.CITY, x.CX_SP])
            .toLowerCase()
            .includes(q.toLowerCase()),
      ),
    [sites.data, q],
  );

  return (
    <View style={s.screen}>
      <View style={{ padding: space(4), paddingBottom: 0 }}>
        <TextInput
          style={s.input}
          placeholder="Search site, city or service provider"
          value={q}
          onChangeText={setQ}
        />
      </View>
      {sites.error ? (
        <View style={s.content}>
          <ErrorView error={sites.error} onRetry={sites.reload} />
        </View>
      ) : null}
      <FlatList
        data={rows}
        keyExtractor={(x) => x.SITE_ID}
        contentContainerStyle={s.content}
        refreshControl={<RefreshControl refreshing={sites.loading} onRefresh={sites.reload} />}
        ListEmptyComponent={sites.loading ? null : <Empty text="No sites assigned to you." />}
        renderItem={({ item }) => {
          const byType: Record<string, number> = item.DOC_BY_TYPE ?? {};
          const docCount: number = item.DOC_COUNT ?? 0;
          const spFiles: number = item.SHAREPOINT_FILES ?? 0;
          const pipelineNeeded: boolean = item.PIPELINE_NEEDED ?? false;
          const pendingUploads: number = item.PENDING_UPLOADS ?? 0;
          const typeEntries = Object.entries(byType);

          return (
            <Card
              onPress={() =>
                router.push({ pathname: '/site/[id]', params: { id: item.SITE_ID } })
              }
            >
              {/* Header row — Site ID + workflow state */}
              <Row style={{ justifyContent: 'space-between' }}>
                <Title>{item.SITE_ID}</Title>
                <Badge text={item.WORKFLOW_STATE} color={colors.primary} />
              </Row>

              {/* Location */}
              <Muted>
                {[
                  item.SITE_NAME,
                  [item.CITY, item.STATE].filter(Boolean).join(', '),
                ]
                  .filter(Boolean)
                  .join(' · ') || 'No location details'}
              </Muted>

              {/* Stream / structure / discrepancies */}
              <Row style={{ marginTop: space(2) }}>
                <Badge text={item.STREAM} color={colors.info} />
                <Badge text={item.STRUCTURE_TYPE} color={colors.muted} />
                {item.OPEN_DISCREPANCIES ? (
                  <Badge text={`${item.OPEN_DISCREPANCIES} open`} color={colors.danger} />
                ) : (
                  <Badge text="no open findings" color={colors.ok} />
                )}
              </Row>

              {/* CX SP / BOM */}
              <Muted style={{ marginTop: space(1) }}>
                {`CX SP: ${item.CX_SP ?? '-'}  |  BOM ${item.CURRENT_BOM_REV ?? '-'}`}
              </Muted>

              {/* ── Document count summary ── */}
              <View
                style={{
                  marginTop: space(3),
                  paddingTop: space(3),
                  borderTopWidth: 1,
                  borderTopColor: colors.border,
                }}
              >
                {/* Total count + pending uploads */}
                <Row style={{ justifyContent: 'space-between', marginBottom: space(2) }}>
                  <Row style={{ gap: space(1.5) }}>
                    <Icon name="file-text" size={14} color={colors.accent} />
                    <Text
                      style={{ fontSize: 13, fontWeight: '700', color: colors.text }}
                    >
                      {docCount > 0
                        ? `${docCount} document${docCount !== 1 ? 's' : ''} registered`
                        : pipelineNeeded
                        ? `${spFiles} file${spFiles !== 1 ? 's' : ''} in SharePoint`
                        : 'No documents registered'}
                    </Text>
                  </Row>
                  {pendingUploads > 0 ? (
                    <Row style={{ gap: space(1) }}>
                      <Icon name="upload-cloud" size={12} color={colors.warn} />
                      <Text style={{ fontSize: 11, color: colors.warn, fontWeight: '600' }}>
                        {`${pendingUploads} pending`}
                      </Text>
                    </Row>
                  ) : null}
                </Row>

                {/* Category pills */}
                {typeEntries.length > 0 ? (
                  <Row style={{ flexWrap: 'wrap', gap: space(1.5) }}>
                    {typeEntries.map(([type, count]) => (
                      <View
                        key={type}
                        style={{
                          flexDirection: 'row',
                          alignItems: 'center',
                          gap: 4,
                          backgroundColor: docColor(type) + '15',
                          borderRadius: 999,
                          paddingHorizontal: 9,
                          paddingVertical: 3,
                        }}
                      >
                        <Text
                          style={{
                            fontSize: 11,
                            fontWeight: '700',
                            color: docColor(type),
                            letterSpacing: 0.2,
                          }}
                        >
                          {type.replace(/_/g, ' ')}
                        </Text>
                        <View
                          style={{
                            backgroundColor: docColor(type),
                            borderRadius: 999,
                            minWidth: 16,
                            height: 16,
                            alignItems: 'center',
                            justifyContent: 'center',
                            paddingHorizontal: 4,
                          }}
                        >
                          <Text style={{ fontSize: 10, fontWeight: '800', color: '#fff' }}>
                            {count}
                          </Text>
                        </View>
                      </View>
                    ))}
                  </Row>
                ) : pipelineNeeded ? (
                  <View
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: space(1.5),
                      backgroundColor: '#FFF7ED',
                      borderRadius: 8,
                      paddingHorizontal: space(2.5),
                      paddingVertical: space(1.5),
                      borderWidth: 1,
                      borderColor: '#FED7AA',
                    }}
                  >
                    <Icon name="zap" size={12} color="#EA580C" />
                    <Text style={{ fontSize: 11, color: '#EA580C', fontWeight: '600', flex: 1 }}>
                      {`${spFiles} file${spFiles !== 1 ? 's' : ''} uploaded · Run pipeline to register documents`}
                    </Text>
                  </View>
                ) : (
                  <Row style={{ gap: space(1.5) }}>
                    <Icon name="alert-circle" size={12} color={colors.muted} />
                    <Muted style={{ fontSize: 11 }}>No documents uploaded yet</Muted>
                  </Row>
                )}
              </View>
            </Card>
          );
        }}
      />
    </View>
  );
}

