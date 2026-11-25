// An A&E engineer's sites: the ones that have redlines or RFIs for the firm, with how many are still open. Opening one shows only its redlines and RFIs.
import { router } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { clean } from '../lib/format';
import { Row } from '../lib/types';
import { useApi } from '../lib/useApi';
import { colors, space } from './theme';
import { Badge, Card, Column, DataTable, EmptyState, ErrorView, Loading, PageHeader, s, SearchBox, Stat } from './ui';

export function AeSites() {
  const sites = useApi<Row[]>('/sites');
  const [query, setQuery] = useState('');
  const list = useMemo(() => {
    const t = query.trim().toLowerCase();
    return [...(sites.data ?? [])]
      .filter((x) => !t || [x.SITE_ID, x.SITE_NAME, x.CITY, x.STATE].some((v) => String(v ?? '').toLowerCase().includes(t)))
      .sort((a, b) => (b.OPEN_REDLINES + b.OPEN_RFIS) - (a.OPEN_REDLINES + a.OPEN_RFIS) || String(a.SITE_ID).localeCompare(String(b.SITE_ID)));
  }, [sites.data, query]);
  const total = (k: string) => (sites.data ?? []).reduce((n, x) => n + (x[k] ?? 0), 0);
  const open = (id: string) => router.push({ pathname: '/site/[id]', params: { id, tab: 'redlines' } });
  const count = (open_: number, all: number) => (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
      <Badge text={`${open_} open`} color={open_ ? colors.warn : colors.neutral} />
      <Text style={{ fontSize: 12, color: colors.muted }}>{`of ${all}`}</Text>
    </View>
  );
  const columns: Column<Row>[] = [
    { key: 'site', title: 'Site', flex: 1.4, render: (x) => (
      <View style={{ gap: 2 }}>
        <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{x.SITE_ID}</Text>
        <Text style={{ fontSize: 12.5, color: colors.muted }} numberOfLines={1}>{clean(x.SITE_NAME)}</Text>
      </View>
    ) },
    { key: 'loc', title: 'Location', flex: 1.2, render: (x) => <Text style={{ fontSize: 13, color: colors.text }} numberOfLines={1}>{[x.CITY, x.STATE].filter(Boolean).join(', ') || 'Not set'}</Text> },
    { key: 'str', title: 'Structure', flex: 1, render: (x) => <Text style={{ fontSize: 13, color: colors.muted }} numberOfLines={1}>{[x.STRUCTURE_TYPE, x.HEIGHT_FT ? `${x.HEIGHT_FT} ft` : null].filter(Boolean).join(' · ') || 'Not set'}</Text> },
    { key: 'red', title: 'Redlines', width: 150, render: (x) => count(x.OPEN_REDLINES, x.REDLINES) },
    { key: 'rfi', title: 'RFIs', width: 150, render: (x) => count(x.OPEN_RFIS, x.RFIS) },
  ];
  return (
    <ScrollView style={s.screen} contentContainerStyle={[s.content, { maxWidth: 1240, width: '100%', alignSelf: 'center' }]}>
      <PageHeader title="Sites" subtitle="The sites with redlines or RFIs for your firm. Open one to work through them." />
      {sites.error ? <ErrorView error={sites.error} onRetry={sites.reload} /> : !sites.data ? <Loading rows={4} /> : (
        <View style={{ gap: space(4) }}>
          <View style={{ flexDirection: 'row', gap: space(3), flexWrap: 'wrap' }}>
            <Stat label="Sites with work" value={sites.data.length} icon="map-pin" />
            <Stat label="Open redlines" value={total('OPEN_REDLINES')} icon="edit-3" color={total('OPEN_REDLINES') ? colors.warn : undefined} />
            <Stat label="Open RFIs" value={total('OPEN_RFIS')} icon="help-circle" color={total('OPEN_RFIS') ? colors.warn : undefined} />
          </View>
          <SearchBox value={query} onChangeText={setQuery} placeholder="Search site, name or city" style={{ maxWidth: 420 }} />
          <DataTable columns={columns} rows={list} keyFor={(x) => x.SITE_ID} onRowPress={(x) => open(x.SITE_ID)} minWidth={820}
            empty={<EmptyState icon="map-pin" title={query ? 'No sites match' : 'No redlines or RFIs for your firm yet'}
              text={query ? 'Change the search to see more sites.' : 'Sites appear here once a redline or an RFI is sent to your firm.'} />} />
        </View>
      )}
    </ScrollView>
  );
}
