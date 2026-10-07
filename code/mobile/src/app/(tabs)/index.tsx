// Dashboard: counts for the signed-in persona's sites (a CX SP sees only its own sites).
import { router } from 'expo-router';
import React from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { colors, space, statusColor } from '../../components/theme';
import { Badge, Card, ErrorView, Loading, Muted, Row, s, Section, Stat, Title } from '../../components/ui';
import { useAuth } from '../../lib/auth';
import { label, money } from '../../lib/format';
import { useApi } from '../../lib/useApi';

interface Dash {
  sites: number; by_state: Record<string, number>; by_stream: Record<string, number>;
  discrepancies: { total: number; by_status: Record<string, number>; by_outcome: Record<string, number>; by_severity: Record<string, number> };
  redlines: Record<string, number>; rfis: Record<string, number>; ehs_open: number; estimate_total_usd: number; inbox_unread: number;
}

function Counts({ data }: { data: Record<string, number> }) {
  return (
    <Row>
      {Object.entries(data).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
        <Badge key={k} text={`${k} ${v}`} color={statusColor(k)} />
      ))}
    </Row>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const d = useApi<Dash>('/sites/dashboard');
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={d.loading} onRefresh={d.reload} />}>
      <Title>{`Hello, ${user?.name}`}</Title>
      <Muted>{`${user?.persona} - ${user?.organisation}`}</Muted>
      {d.error ? <ErrorView error={d.error} onRetry={d.reload} /> : !d.data ? <Loading /> : (
        <>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(2), marginTop: space(4) }}>
            <Stat label="Sites" value={d.data.sites} />
            <Stat label="Open discrepancies" value={d.data.discrepancies.by_status.OPEN ?? 0} color={colors.danger} />
            <Stat label="Open EH&S alerts" value={d.data.ehs_open} color={d.data.ehs_open ? colors.warn : undefined} />
            <Stat label="Unread inbox" value={d.data.inbox_unread} />
            <Stat label="Estimated total" value={money(d.data.estimate_total_usd)} />
          </View>
          <Section title="Sites by workflow state">
            <Card onPress={() => router.push('/(tabs)/sites')}><Counts data={d.data.by_state} /></Card>
          </Section>
          <Section title="Scoping streams"><Card><Counts data={d.data.by_stream} /></Card></Section>
          <Section title="Discrepancies">
            <Card onPress={() => router.push('/(tabs)/queue')}>
              <Muted>By status</Muted><Counts data={d.data.discrepancies.by_status} />
              <Muted style={{ marginTop: space(2) }}>By severity</Muted><Counts data={d.data.discrepancies.by_severity} />
              <Muted style={{ marginTop: space(2) }}>By outcome</Muted>
              <Row>{Object.entries(d.data.discrepancies.by_outcome).map(([k, v]) => <Badge key={k} text={`${label(k)} ${v}`} color={colors.primary} />)}</Row>
            </Card>
          </Section>
          <Section title="Redlines and RFIs">
            <Card><Muted>Redlines</Muted><Counts data={d.data.redlines} /><Muted style={{ marginTop: space(2) }}>RFIs</Muted><Counts data={d.data.rfis} /></Card>
          </Section>
        </>
      )}
    </ScrollView>
  );
}
