import { useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';
import { AppShell } from '../../components/NavBar';
import { BomView } from '../../components/site/BomView';
import { Discrepancies } from '../../components/site/Discrepancies';
import { Handshake } from '../../components/site/Handshake';
import { Overview } from '../../components/site/Overview';
import { Pipeline } from '../../components/site/Pipeline';
import { ProviderBom, ProviderDrawings, ProviderReview, ProviderScope } from '../../components/site/Provider';
import { Redlines } from '../../components/site/Redlines';
import { colors, space } from '../../components/theme';
import { Badge, ErrorView, Icon, IconName, Loading, s, Tabs } from '../../components/ui';
import { useAuth } from '../../lib/auth';
import { clean } from '../../lib/format';
import { SiteDetail } from '../../lib/types';
import { useApi } from '../../lib/useApi';

type Tab = 'overview' | 'pipeline' | 'discrepancies' | 'redlines' | 'bom' | 'handshake' | 'drawings' | 'scope';
type TabDef = { key: Tab; label: string; icon: IconName };

const ALL_TABS: TabDef[] = [
  { key: 'overview', label: 'Overview', icon: 'info' },
  { key: 'pipeline', label: 'Pipeline', icon: 'git-commit' },
  { key: 'handshake', label: 'Handshake & Scope', icon: 'check-circle' },
  { key: 'drawings', label: 'Drawings', icon: 'file-text' },
  { key: 'scope', label: 'Scope of work', icon: 'layers' },
  { key: 'discrepancies', label: 'Discrepancies', icon: 'alert-triangle' },
  { key: 'redlines', label: 'Redlines & RFIs', icon: 'edit-3' },
  { key: 'bom', label: 'Bill of materials', icon: 'list' },
];
// A service provider is given the site, the final drawings, and from the handshake the scope of work and the BOM; none of the scoping work.
const SP_TABS: Tab[] = ['overview', 'drawings', 'scope', 'bom'];

function SiteHeader({ id, d }: { id: string; d: SiteDetail | null }) {
  const site = d?.site ?? {};
  const where = [site.SITE_NAME, [site.CITY, site.STATE].filter(Boolean).join(', ')].filter(Boolean).join('  ·  ');
  const facts: { icon: IconName; text?: string }[] = [
    { icon: 'layers', text: site.STRUCTURE_TYPE },
    { icon: 'arrow-up', text: site.HEIGHT_FT ? `${site.HEIGHT_FT} ft` : undefined },
    { icon: 'briefcase', text: clean(site.CX_SP) },
    { icon: 'file-text', text: d && d.documents.length ? `${d.documents.length} document${d.documents.length === 1 ? '' : 's'}` : undefined },
  ].filter((f) => f.text);
  return (
    <View style={{ backgroundColor: '#fff', paddingHorizontal: space(6), paddingTop: space(5) }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), flexWrap: 'wrap' }}>
        <Text style={{ fontSize: 22, fontWeight: '600', color: colors.text, letterSpacing: -0.3 }}>{id}</Text>
        {site.WORKFLOW_STATE ? <Badge text={site.WORKFLOW_STATE} color={colors.info} dot /> : null}
        {site.STREAM ? <Badge text={site.STREAM} color={colors.neutral} /> : null}
      </View>
      <Text style={[s.muted, { marginTop: 4 }]}>{where || 'No location details'}</Text>
      {facts.length ? (
        <View style={{ flexDirection: 'row', gap: space(5), marginTop: space(3), flexWrap: 'wrap' }}>
          {facts.map((f) => (
            <View key={f.icon} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Icon name={f.icon} size={13} color={colors.faint} />
              <Text style={{ fontSize: 12.5, color: colors.muted }}>{f.text}</Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

export default function Site() {
  const { user } = useAuth();
  const isAe = user?.role === 'AE_ENGINEER';
  const isSp = user?.role === 'CX_SP';
  const tabs: TabDef[] = isAe
    ? ALL_TABS.filter((t) => t.key === 'redlines')
    : isSp
      ? SP_TABS.map((k) => ALL_TABS.find((t) => t.key === k)!)
      : ALL_TABS.filter((t) => t.key !== 'drawings' && t.key !== 'scope');
  const { id, tab: initial } = useLocalSearchParams<{ id: string; tab?: Tab }>();
  const defaultTab: Tab = isAe
    ? 'redlines'
    : isSp
      ? 'overview'
      : initial && ALL_TABS.some((t) => t.key === initial) ? (initial as Tab) : 'overview';
  const [tab, setTab] = useState<Tab>(defaultTab);
  const activeTab: Tab = isAe ? 'redlines' : tab;
  const [key, setKey] = useState(0);
  const d = useApi<SiteDetail>(`/sites/${id}`);

  return (
    <AppShell crumbs={isAe ? [{ label: 'Redlines & RFIs', href: '/(tabs)/rfis' }, { label: id }]
      : [{ label: 'Sites', href: '/(tabs)/sites' }, { label: id }, { label: activeTab === 'pipeline' ? 'Pipeline run' : tabs.find((t) => t.key === activeTab)?.label ?? '' }]}>
      <View style={[s.screen, { flex: 1 }]}>
        <View style={{ backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <SiteHeader id={id} d={d.data} />
          <Tabs tabs={tabs} value={activeTab} onChange={setTab} style={{ paddingHorizontal: space(6), marginTop: space(4), marginBottom: space(4) }} />
        </View>
        <ScrollView
          contentContainerStyle={[s.content, { maxWidth: activeTab === 'pipeline' ? 1640 : activeTab === 'bom' || activeTab === 'handshake' ? 1440 : 1240, width: '100%', alignSelf: 'center' }]}
          refreshControl={<RefreshControl refreshing={d.loading} onRefresh={() => { void d.reload(); setKey((k) => k + 1); }} />}
        >
          {d.error ? (
            <ErrorView error={d.error} onRetry={d.reload} />
          ) : !d.data ? (
            <Loading />
          ) : (
            <View key={`${activeTab}-${key}`}>
              {!isAe && activeTab === 'overview' && <Overview d={d.data} reload={d.reload} />}
              {!isAe && !isSp && activeTab === 'pipeline' && <Pipeline siteId={id} siteName={d.data.site?.SITE_NAME} onFinished={d.reload} onOpenTab={(t) => setTab(t)} />}
              {!isAe && !isSp && activeTab === 'handshake' && <Handshake siteId={id} />}
              {!isAe && !isSp && activeTab === 'discrepancies' && <Discrepancies siteId={id} />}
              {!isSp && activeTab === 'redlines' && <Redlines siteId={id} />}
              {!isAe && !isSp && activeTab === 'bom' && <BomView siteId={id} />}
              {isSp && activeTab === 'drawings' && <ProviderDrawings siteId={id} />}
              {isSp && activeTab === 'scope' && <ProviderScope siteId={id} />}
              {isSp && activeTab === 'bom' && <ProviderBom siteId={id} />}
              {isSp && <View style={{ marginTop: space(4) }}><ProviderReview siteId={id} /></View>}
            </View>
          )}
        </ScrollView>
      </View>
    </AppShell>
  );
}
