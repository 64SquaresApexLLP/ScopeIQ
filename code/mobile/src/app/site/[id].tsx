import { Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { BomRevisions } from '../../components/site/Bom';
import { Delta } from '../../components/site/Delta';
import { Discrepancies } from '../../components/site/Discrepancies';
import { Documents } from '../../components/site/Documents';
import { Estimate } from '../../components/site/Estimate';
import { Evidence } from '../../components/site/Evidence';
import { Overview } from '../../components/site/Overview';
import { Pipeline } from '../../components/site/Pipeline';
import { Redlines } from '../../components/site/Redlines';
import { Button, Chips, ErrorView, Loading, Row, s } from '../../components/ui';
import { api, ApiError } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { SiteDetail } from '../../lib/types';
import { useApi } from '../../lib/useApi';

type Tab = 'overview' | 'pipeline' | 'documents' | 'discrepancies' | 'delta' | 'bom' | 'redlines' | 'estimate' | 'evidence';
const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' }, { key: 'pipeline', label: 'Pipeline' }, { key: 'discrepancies', label: 'Discrepancies' }, { key: 'delta', label: 'Delta' },
  { key: 'bom', label: 'BOM' }, { key: 'redlines', label: 'Redlines & RFIs' }, { key: 'estimate', label: 'Drivers & estimate' },
  { key: 'evidence', label: 'Drone evidence' }, { key: 'documents', label: 'Documents' },
];

export default function Site() {
  const { id, tab: initial } = useLocalSearchParams<{ id: string; tab?: Tab }>();
  const [tab, setTab] = useState<Tab>(initial ?? 'overview');
  const [key, setKey] = useState(0);                       // bump to remount tab content after a pipeline run
  const d = useApi<SiteDetail>(`/sites/${id}`);
  const { can } = useAuth();
  const [running, setRunning] = useState(false);
  const [runErr, setRunErr] = useState<ApiError | null>(null);

  // start the run in the background and follow it on the Pipeline tab
  const run = async () => {
    setRunning(true);
    setRunErr(null);
    try {
      await api.post(`/pipeline/sites/${id}/start`);
      setTab('pipeline');
      setKey((k) => k + 1);
    } catch (e) {
      setRunErr(e as ApiError);
    } finally {
      setRunning(false);
    }
  };

  return (
    <View style={s.screen}>
      <Stack.Screen options={{ title: id }} />
      <View style={{ paddingHorizontal: 16 }}><Chips<Tab> value={tab} onChange={setTab} options={TABS} /></View>
      <ScrollView contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={d.loading} onRefresh={() => { void d.reload(); setKey((k) => k + 1); }} />}>
        {can('SCOPER', 'REVIEWER') && tab === 'overview' ? (
          <Row style={{ marginBottom: 8 }}><Button small kind="secondary" title={running ? 'Starting...' : 'Re-run pipeline'} disabled={running} onPress={run} /></Row>
        ) : null}
        {runErr ? <ErrorView error={runErr} /> : null}
        {d.error ? <ErrorView error={d.error} onRetry={d.reload} /> : !d.data ? <Loading /> : (
          <View key={`${tab}-${key}`}>
            {tab === 'overview' && <Overview d={d.data} reload={d.reload} />}
            {tab === 'pipeline' && <Pipeline siteId={id} onFinished={d.reload} />}
            {tab === 'documents' && <Documents siteId={id} />}
            {tab === 'discrepancies' && <Discrepancies siteId={id} />}
            {tab === 'delta' && <Delta rows={d.data.delta} />}
            {tab === 'bom' && <BomRevisions siteId={id} />}
            {tab === 'redlines' && <Redlines siteId={id} />}
            {tab === 'estimate' && <Estimate siteId={id} />}
            {tab === 'evidence' && <Evidence siteId={id} />}
          </View>
        )}
      </ScrollView>
    </View>
  );
}
