import { Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { Discrepancies } from '../../components/site/Discrepancies';
import { Overview } from '../../components/site/Overview';
import { Pipeline } from '../../components/site/Pipeline';
import { Redlines } from '../../components/site/Redlines';
import { Chips, ErrorView, Loading, s } from '../../components/ui';
import { useAuth } from '../../lib/auth';
import { SiteDetail } from '../../lib/types';
import { useApi } from '../../lib/useApi';

type Tab = 'overview' | 'pipeline' | 'discrepancies' | 'redlines';
const ALL_TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'pipeline', label: 'Pipeline' },
  { key: 'discrepancies', label: 'Discrepancies' },
  { key: 'redlines', label: 'Redlines & RFIs' },
];

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
  const [key, setKey] = useState(0); // bump to remount tab content after a pipeline run
  const d = useApi<SiteDetail>(`/sites/${id}`);

  return (
    <View style={s.screen}>
      <Stack.Screen options={{ title: id }} />
      <View style={{ paddingHorizontal: 16 }}>
        <Chips<Tab> value={activeTab} onChange={setTab} options={tabs} />
      </View>
      <ScrollView
        contentContainerStyle={s.content}
        refreshControl={
          <RefreshControl
            refreshing={d.loading}
            onRefresh={() => {
              void d.reload();
              setKey((k) => k + 1);
            }}
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

