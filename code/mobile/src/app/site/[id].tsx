import { Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { BomRevisions } from '../../components/site/Bom';
import { Delta } from '../../components/site/Delta';
import { Discrepancies } from '../../components/site/Discrepancies';
import { Documents } from '../../components/site/Documents';
import { Estimate } from '../../components/site/Estimate';
import { Evidence } from '../../components/site/Evidence';
import { Overview } from '../../components/site/Overview';
import { Pipeline } from '../../components/site/Pipeline';
import { Redlines } from '../../components/site/Redlines';
import { colors, space } from '../../components/theme';
import { Button, Card, Chips, ErrorView, Icon, IconBadge, Loading, Row, s } from '../../components/ui';
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
  const [runSuccess, setRunSuccess] = useState<string | null>(null);

  // Run the scoping pipeline dynamically and stay on the Pipeline tab to observe stage-by-stage execution
  const run = async () => {
    setRunning(true);
    setRunErr(null);
    setRunSuccess(null);
    setTab('pipeline');
    try {
      await api.post(`/pipeline/sites/${id}/start`);
      await d.reload();
      setKey((k) => k + 1);
    } catch (e) {
      try {
        await api.post(`/pipeline/sites/${id}/run`);
        await d.reload();
        setKey((k) => k + 1);
      } catch (err2) {
        setRunErr(e as ApiError);
      }
    } finally {
      setRunning(false);
    }
  };

  return (
    <View style={s.screen}>
      <Stack.Screen options={{ title: id }} />
      <View style={{ paddingHorizontal: 16 }}><Chips<Tab> value={tab} onChange={setTab} options={TABS} /></View>
      <ScrollView contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={d.loading} onRefresh={() => { void d.reload(); setKey((k) => k + 1); }} />}>
        {can('SCOPER', 'REVIEWER', 'ADMIN') ? (
          <Card style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: space(4), marginBottom: space(3.5), borderColor: '#CBD5E8', borderWidth: 1, backgroundColor: '#fff' }}>
            <View style={{ flex: 1, marginRight: space(3) }}>
              <Row style={{ alignItems: 'center', gap: space(2) }}>
                <IconBadge name="cpu" color={colors.accent} size={32} />
                <Text style={{ fontSize: 16, fontWeight: '800', color: colors.text }}>Scoping Pipeline</Text>
              </Row>
              <Text style={{ fontSize: 12.5, color: colors.muted, marginTop: 4 }}>
                Runs document intake, enforces latest revision selection across drawings and specs, and executes cross-consistency rules.
              </Text>
            </View>
            <Button
              title={running ? 'Running Pipeline...' : 'Run Pipeline'}
              disabled={running}
              onPress={run}
            />
          </Card>
        ) : null}
        {runSuccess ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2.5), padding: space(3.5), borderRadius: 12, backgroundColor: '#F0FBF4', borderWidth: 1, borderColor: '#C6EBD3', marginBottom: space(3.5) }}>
            <Icon name="check-circle" size={18} color={colors.ok} />
            <Text style={{ color: '#2B6343', fontSize: 13, fontWeight: '700', flex: 1 }}>{runSuccess}</Text>
            <Pressable onPress={() => setRunSuccess(null)} style={{ padding: 4 }}><Icon name="x" size={14} color="#2B6343" /></Pressable>
          </View>
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
