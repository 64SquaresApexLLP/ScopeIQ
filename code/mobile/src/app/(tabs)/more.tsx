import { router } from 'expo-router';
import React, { useState } from 'react';
import { ScrollView } from 'react-native';
import { Button, Card, ErrorView, KV, Muted, Row, s, Section, Title } from '../../components/ui';
import { api, ApiError } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { settings } from '../../lib/config';

export default function More() {
  const { user, logout, can } = useAuth();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const runAll = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ site_id: string; status: string }[]>('/pipeline/run', { site_ids: null });
      setResult(r.map((x) => `${x.site_id}: ${x.status}`).join('\n'));
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content}>
      <Card>
        <Title>{user?.name}</Title>
        <KV k="Role" v={user?.role} />
        <KV k="Persona" v={user?.persona} />
        <KV k="Organisation" v={user?.organisation} />
        <KV k="Key screens" v={user?.key_screens} />
      </Card>
      {can('SCOPER', 'REVIEWER') ? (
        <Section title="Pipeline">
          <Card>
            <Muted>Re-run ingest, extraction, reconciliation, BOM generation and estimates for every site. Human decisions are kept.</Muted>
            <Row style={{ marginTop: 8 }}><Button title={busy ? 'Running... (OCR sites take a while)' : 'Run all sites'} disabled={busy} onPress={runAll} /></Row>
            {result ? <Muted style={{ marginTop: 8 }}>{result}</Muted> : null}
            {error ? <ErrorView error={error} /> : null}
          </Card>
        </Section>
      ) : null}
      <Section title="Data and governance">
        {can('REVIEWER', 'ERICSSON') ? <Card onPress={() => router.push('/audit')}><Title>Audit trail</Title><Muted>Who changed what, when and why</Muted></Card> : null}
        <Card onPress={() => router.push('/reference')}><Title>Reference data</Title><Muted>Catalog, kit rules, consistency rules, rate card, workflow</Muted></Card>
        {can('ADMIN') ? <Card onPress={() => router.push('/logs')}><Title>Logs and configuration</Title><Muted>Application and error logs, runtime settings</Muted></Card> : null}
      </Section>
      <Section title="App">
        <Card>
          <KV k="Environment" v={settings.env} />
          <KV k="API" v={settings.apiUrl} />
          <KV k="Log level" v={`${settings.logLevel} (server gets ${settings.remoteLogLevel}+)`} />
        </Card>
        <Button title="Sign out" kind="secondary" onPress={logout} />
      </Section>
    </ScrollView>
  );
}
