import { router, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { Discrepancies } from '../../components/site/Discrepancies';
import { Overview } from '../../components/site/Overview';
import { Pipeline } from '../../components/site/Pipeline';
import { Redlines } from '../../components/site/Redlines';
import { brandGradient, colors, space } from '../../components/theme';
import { ErrorView, Icon, Loading, s } from '../../components/ui';
import { NavBar } from '../../components/NavBar';
import { useAuth } from '../../lib/auth';
import { SiteDetail } from '../../lib/types';
import { useApi } from '../../lib/useApi';

type Tab = 'overview' | 'pipeline' | 'discrepancies' | 'redlines';

const ALL_TABS: { key: Tab; label: string; icon: any }[] = [
  { key: 'overview', label: 'Overview', icon: 'info' },
  { key: 'pipeline', label: 'Pipeline', icon: 'zap' },
  { key: 'discrepancies', label: 'Discrepancies', icon: 'alert-triangle' },
  { key: 'redlines', label: 'Redlines & RFIs', icon: 'edit-3' },
];

function SiteTabBar({ tabs, tab, onChange }: { tabs: typeof ALL_TABS; tab: Tab; onChange: (t: Tab) => void }) {
  return (
    <View style={{ backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: colors.border }}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ flexDirection: 'row', paddingHorizontal: space(4), gap: space(1) }}
      >
        {tabs.map((t) => {
          const active = tab === t.key;
          return (
            <Pressable
              key={t.key}
              onPress={() => onChange(t.key)}
              style={({ pressed }: any) => ({
                flexDirection: 'row',
                alignItems: 'center',
                gap: space(1.5),
                paddingHorizontal: space(3.5),
                paddingVertical: space(3),
                borderBottomWidth: 2.5,
                borderBottomColor: active ? colors.accent : 'transparent',
                opacity: pressed ? 0.7 : 1,
                marginBottom: -1,
              })}
            >
              <Icon name={t.icon} size={14} color={active ? colors.accent : colors.muted} />
              <Text style={{
                fontSize: 13.5,
                fontWeight: active ? '700' : '500',
                color: active ? colors.accent : colors.muted,
                letterSpacing: 0.1,
              }}>
                {t.label}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

export default function Site() {
  const { user } = useAuth();
  const isAe = user?.role === 'AE_ENGINEER';
  const tabs = isAe ? ALL_TABS.filter((t) => t.key === 'redlines') : ALL_TABS;

  const { id, tab: initial } = useLocalSearchParams<{ id: string; tab?: Tab }>();

  const defaultTab: Tab = isAe
    ? 'redlines'
    : initial && ['overview', 'pipeline', 'discrepancies', 'redlines'].includes(initial as Tab)
      ? (initial as Tab)
      : 'overview';

  const [tab, setTab] = useState<Tab>(defaultTab);
  const activeTab: Tab = isAe ? 'redlines' : tab;
  const [key, setKey] = useState(0);
  const d = useApi<SiteDetail>(`/sites/${id}`);

  return (
    <View style={[s.screen, { flex: 1 }]}>
      <NavBar />

      {/* Site header breadcrumb */}
      <View style={[{ paddingHorizontal: space(5), paddingVertical: space(3), flexDirection: 'row', alignItems: 'center', gap: space(2) }, brandGradient]}>
        <Pressable onPress={() => router.back()} style={{ flexDirection: 'row', alignItems: 'center', gap: space(1) }}>
          <Icon name="chevron-left" size={16} color="rgba(255,255,255,0.75)" />
          <Text style={{ color: 'rgba(255,255,255,0.75)', fontSize: 13, fontWeight: '500' }}>Sites</Text>
        </Pressable>
        <Icon name="chevron-right" size={13} color="rgba(255,255,255,0.4)" />
        <Text style={{ color: '#fff', fontSize: 13, fontWeight: '700' }}>{id}</Text>
      </View>

      {/* Sub tab bar */}
      <SiteTabBar tabs={tabs} tab={activeTab} onChange={setTab} />

      <ScrollView
        contentContainerStyle={[s.content, { maxWidth: 1100, width: '100%', alignSelf: 'center' }]}
        refreshControl={
          <RefreshControl
            refreshing={d.loading}
            onRefresh={() => { void d.reload(); setKey((k) => k + 1); }}
          />
        }
      >
        {d.error ? (
          <ErrorView error={d.error} onRetry={d.reload} />
        ) : !d.data ? (
          <Loading />
        ) : (
          <View key={`${activeTab}-${key}`}>
            {!isAe && activeTab === 'overview' && <Overview d={d.data} reload={d.reload} />}
            {!isAe && activeTab === 'pipeline' && <Pipeline siteId={id} onFinished={d.reload} />}
            {!isAe && activeTab === 'discrepancies' && <Discrepancies siteId={id} />}
            {activeTab === 'redlines' && <Redlines siteId={id} />}
          </View>
        )}
      </ScrollView>
    </View>
  );
}
