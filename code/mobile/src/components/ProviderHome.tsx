// A service provider's home: the sites assigned to its company, and where each stands. Nothing of the scoping work.
import { router } from 'expo-router';
import React from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { useAuth } from '../lib/auth';
import { clean } from '../lib/format';
import { Row } from '../lib/types';
import { useApi } from '../lib/useApi';
import { colors, radius, shadow, space } from './theme';
import { Badge, Card, EmptyState, ErrorView, Icon, Loading, PageHeader, s } from './ui';

const PHASE: Record<string, { text: string; color: string }> = {
  PENDING: { text: 'Scope and BOM being prepared', color: colors.neutral },
  REVIEW: { text: 'Waiting for your review', color: colors.warn },
  AGREED: { text: 'Agreed, final approval to come', color: colors.info },
  APPROVED: { text: 'Approved', color: colors.ok },
};

export function ProviderHome() {
  const { user } = useAuth();
  const sites = useApi<Row[]>('/sites');
  const open = (id: string) => router.push({ pathname: '/site/[id]', params: { id } });
  return (
    <ScrollView style={s.screen} contentContainerStyle={[s.content, { maxWidth: 1100, width: '100%', alignSelf: 'center' }]}>
      <PageHeader title="Your sites" subtitle={clean(user?.organisation) ? `Sites assigned to ${clean(user?.organisation)}` : 'Sites assigned to you'} />
      {sites.error ? <ErrorView error={sites.error} onRetry={sites.reload} /> : !sites.data ? <Loading /> : sites.data.length === 0 ? (
        <Card><EmptyState icon="map-pin" title="No sites yet" text="Sites appear here once they are assigned to your company." /></Card>
      ) : (
        <View style={{ gap: space(3) }}>
          {sites.data.map((x) => (
            <Pressable key={x.SITE_ID} onPress={() => open(x.SITE_ID)} accessibilityRole="button"
              style={({ hovered }: any) => [{ backgroundColor: '#fff', borderRadius: radius.xl, borderWidth: 1, borderColor: hovered ? colors.borderStrong : colors.border, padding: space(4),
                flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: space(3) }, shadow as any]}>
              <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center' }}>
                <Icon name="map-pin" size={18} color={colors.accent} />
              </View>
              <View style={{ flex: 1, minWidth: 220 }}>
                <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: space(2), flexWrap: 'wrap' }}>
                  <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>{x.SITE_ID}</Text>
                  {x.SITE_NAME ? <Text style={{ fontSize: 13.5, color: colors.muted }}>{x.SITE_NAME}</Text> : null}
                </View>
                <Text style={{ fontSize: 13, color: colors.muted, marginTop: 2 }} numberOfLines={1}>
                  {[clean(x.ADDRESS), [x.CITY, x.STATE].filter(Boolean).join(', ')].filter(Boolean).join(' · ') || 'Location not available'}
                </Text>
                {x.STRUCTURE_TYPE ? <Text style={{ fontSize: 12.5, color: colors.faint, marginTop: 1 }}>{[x.STRUCTURE_TYPE, x.HEIGHT_FT ? `${x.HEIGHT_FT} ft` : null].filter(Boolean).join(' · ')}</Text> : null}
              </View>
              <View style={{ gap: 6, alignItems: 'flex-end' }}>
                <Badge text={x.DRAWINGS_READY ? 'Drawings ready' : 'Drawings pending'} color={x.DRAWINGS_READY ? colors.ok : colors.neutral} dot />
                <Badge text={PHASE[x.PHASE]?.text ?? 'Being prepared'} color={PHASE[x.PHASE]?.color ?? colors.neutral} dot />
              </View>
              <Icon name="chevron-right" size={18} color={colors.faint} />
            </Pressable>
          ))}
        </View>
      )}
    </ScrollView>
  );
}
