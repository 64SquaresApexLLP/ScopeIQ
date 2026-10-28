// Dashboard: counts for the signed-in persona's sites (a CX SP sees only its own sites).
import { Redirect, router, useFocusEffect } from 'expo-router';
import React, { useCallback, useRef } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { colors, space, statusColor } from '../../components/theme';
import { Badge, Card, ErrorView, Hero, Icon, IconBadge, IconName, Loading, Muted, Row, s, Stat } from '../../components/ui';
import { useAuth } from '../../lib/auth';
import { label, money, roleLabel } from '../../lib/format';
import { useApi } from '../../lib/useApi';

interface Dash {
  sites: number; by_state: Record<string, number>; by_stream: Record<string, number>;
  discrepancies: { total: number; by_status: Record<string, number>; by_outcome: Record<string, number>; by_severity: Record<string, number> };
  redlines: Record<string, number>; rfis: Record<string, number>; ehs_open: number; estimate_total_usd: number; inbox_unread: number;
}

function Counts({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return <Muted>None yet</Muted>;
  return <Row>{entries.map(([k, v]) => <Badge key={k} text={`${label(k)} · ${v}`} color={statusColor(k)} />)}</Row>;
}

function Panel({ icon, title, hint, onPress, children }: { icon: IconName; title: string; hint?: string; onPress?: () => void; children: React.ReactNode }) {
  return (
    <View style={{ flexGrow: 1, flexBasis: 300, alignSelf: 'flex-start' }}>
      <Card onPress={onPress}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), marginBottom: space(3) }}>
          <IconBadge name={icon} size={34} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontWeight: '700', fontSize: 15, color: colors.text }}>{title}</Text>
            {hint ? <Text style={{ fontSize: 12, color: colors.muted }}>{hint}</Text> : null}
          </View>
          {onPress ? <Icon name="chevron-right" size={18} /> : null}
        </View>
        <View style={{ gap: space(2.5) }}>{children}</View>
      </Card>
    </View>
  );
}

const Sub = ({ children }: { children: string }) => <Text style={{ fontSize: 11, fontWeight: '800', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.8 }}>{children}</Text>;

export default function Dashboard() {
  const { user, can } = useAuth();
  if (user?.role === 'AE_ENGINEER') {
    return <Redirect href="/(tabs)/rfis" />;
  }
  const d = useApi<Dash>('/sites/dashboard');
  const firstFocus = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (firstFocus.current) {
        firstFocus.current = false;
        return;
      }
      d.reload(true);
    }, [d.reload]),
  );
  return (
    <ScrollView style={s.screen} contentContainerStyle={[s.content, { maxWidth: 1100, width: '100%', alignSelf: 'center' }]} refreshControl={<RefreshControl refreshing={d.loading} onRefresh={d.reload} />}>
      <Hero icon="grid" title="Welcome back" subtitle={`Signed in as ${roleLabel(user?.role)}`} />
      {d.error ? <ErrorView error={d.error} onRetry={d.reload} /> : !d.data ? <Loading /> : (
        <>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(3), marginBottom: space(4) }}>
            <Stat icon="map-pin" label="Sites" value={d.data.sites} />
            <Stat icon="alert-circle" label="Open discrepancies" value={d.data.discrepancies.by_status.OPEN ?? 0} color={colors.danger} />
            <Stat icon="shield" label="Open EH&S alerts" value={d.data.ehs_open} color={d.data.ehs_open ? colors.warn : colors.ok} />
            <Stat icon="inbox" label="Unread inbox" value={d.data.inbox_unread} color={colors.info} />
            <Stat icon="dollar-sign" label="Estimated total" value={money(d.data.estimate_total_usd)} color={colors.ok} />
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', columnGap: space(3), alignItems: 'flex-start' }}>
            <Panel icon="map-pin" title="Sites" hint="By workflow state" onPress={() => router.push('/(tabs)/sites')}>
              <Counts data={d.data.by_state} />
              <Sub>Streams</Sub>
              <Counts data={d.data.by_stream} />
            </Panel>
            <Panel icon="alert-triangle" title="Discrepancies" hint="Findings waiting for a decision" onPress={() => router.push('/(tabs)/queue')}>
              <Sub>Status</Sub><Counts data={d.data.discrepancies.by_status} />
              <Sub>Severity</Sub><Counts data={d.data.discrepancies.by_severity} />
            </Panel>
            <Panel
              icon="edit-3"
              title="Redlines and RFIs"
              hint="Corrections and questions"
              onPress={can('ADMIN', 'AE_ENGINEER', 'SCOPER', 'REVIEWER', 'ERICSSON') ? () => router.push('/(tabs)/rfis') : undefined}
            >
              <Sub>Redlines</Sub><Counts data={d.data.redlines} />
              <Sub>RFIs</Sub><Counts data={d.data.rfis} />
            </Panel>
          </View>
          {can('ADMIN') ? (
            <Pressable onPress={() => router.push('/(tabs)/sharepoint')} accessibilityRole="button">
              <Card style={{ flexDirection: 'row', alignItems: 'center', gap: space(3) }}>
                <IconBadge name="upload-cloud" color={colors.accent2} size={40} />
                <View style={{ flex: 1 }}>
                  <Text style={{ fontWeight: '700', color: colors.text }}>Add documents to a site</Text>
                  <Muted>Upload RFDS, drawings, MA/SA, BOM and drone files to SharePoint</Muted>
                </View>
                <Icon name="arrow-right" size={18} color={colors.accent} />
              </Card>
            </Pressable>
          ) : null}
        </>
      )}
    </ScrollView>
  );
}
