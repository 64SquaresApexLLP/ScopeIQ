// Admin: create a site. This creates its SharePoint folder and the site record; the site then appears for uploads.
import { router } from 'expo-router';
import React, { useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';
import { ScoperLogins } from '../../components/admin/ScoperLogins';
import { colors, space } from '../../components/theme';
import { Badge, Button, Card, Chips, ErrorView, Hero, Icon, IconBadge, Muted, s } from '../../components/ui';
import { api, ApiError } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { getLogger } from '../../lib/logger';
import { Row as R } from '../../lib/types';
import { mutateApi, useApi } from '../../lib/useApi';

const log = getLogger('admin');
const STREAMS = ['BOM', 'DESIGN', 'DEPLOYMENT'] as const;
const STRUCTS = ['Monopole', 'Self-support tower', 'Guyed tower', 'Rooftop'] as const;
const PH = '#A9B3C2';

function Field({ label, hint, error, children, flex = 1 }: { label: string; hint?: string; error?: string; children: React.ReactNode; flex?: number }) {
  return (
    <View style={{ flex, minWidth: 120 }}>
      <Text style={{ fontSize: 12.5, fontWeight: '700', color: colors.text, marginBottom: 6 }}>{label}</Text>
      {children}
      {error ? <Text style={{ fontSize: 12, color: colors.danger, marginTop: 4 }}>{error}</Text> : hint ? <Text style={{ fontSize: 12, color: colors.muted, marginTop: 4 }}>{hint}</Text> : null}
    </View>
  );
}

export default function Admin() {
  const { can } = useAuth();
  const sites = useApi<{ location: string; sites: R[] }>('/sharepoint/sites');
  const [siteId, setSiteId] = useState('');
  const [name, setName] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('TX');
  const [more, setMore] = useState(false);
  const [height, setHeight] = useState('');
  const [stream, setStream] = useState<(typeof STREAMS)[number]>('BOM');
  const [struct, setStruct] = useState<(typeof STRUCTS)[number]>('Monopole');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [created, setCreated] = useState<{ id: string; path: string } | null>(null);
  const [section, setSection] = useState<'sites' | 'logins'>('sites');

  if (!can('ADMIN')) {
    return (
      <View style={[s.screen, { alignItems: 'center', justifyContent: 'center', padding: space(8) }]}>
        <IconBadge name="lock" color={colors.muted} size={56} />
        <Text style={{ fontWeight: '800', fontSize: 18, color: colors.text, marginTop: space(3) }}>Administrators only</Text>
        <Muted>Only the platform administrator can create sites.</Muted>
      </View>
    );
  }

  const idOk = /^[A-Z]{4}\d{4}$/.test(siteId);
  const valid = idOk && name.trim().length >= 2 && city.trim().length >= 1 && state.trim().length === 2;

  const create = async () => {
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const res = await api.post<R>('/admin/sites', {
        site_id: siteId, site_name: name.trim(), city: city.trim(), state: state.trim().toUpperCase(), stream, structure_type: struct,
        height_ft: height ? Number(height) : null,
      });
      setCreated({ id: res.site.SITE_ID, path: res.sharepoint.path });
      log.info(`created site ${siteId}`);
      setSiteId(''); setName(''); setCity(''); setHeight('');
      sites.reload();
      mutateApi('/sites');
      mutateApi('/sharepoint/sites');
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView style={s.screen} contentContainerStyle={[s.content, { maxWidth: 820, width: '100%', alignSelf: 'center' }]}
      refreshControl={<RefreshControl refreshing={sites.loading} onRefresh={sites.reload} />}>
      <View style={{ marginBottom: space(4) }}>
        <Chips value={section} onChange={setSection} options={[{ key: 'sites', label: 'Sites' }, { key: 'logins', label: 'Scoper logins' }]} />
      </View>
      {section === 'logins' ? <ScoperLogins /> : <>
      <Hero icon="settings" title="Create a site" subtitle="Adds the site and its SharePoint folder so documents can be uploaded." />

      <Card style={{ padding: space(5) }}>
        <View style={{ gap: space(4) }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(4) }}>
            <Field label="Site ID" hint="4 letters + 4 digits" error={siteId && !idOk ? 'Use 4 letters then 4 digits, e.g. TXDA1024' : undefined}>
              <TextInput style={s.input} placeholder="TXDA1024" placeholderTextColor={PH} value={siteId} onChangeText={(t) => setSiteId(t.toUpperCase())} autoCapitalize="characters" maxLength={8} />
            </Field>
            <Field label="Site name" flex={2}>
              <TextInput style={s.input} placeholder="Lakewood Heights" placeholderTextColor={PH} value={name} onChangeText={setName} />
            </Field>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(4) }}>
            <Field label="City" flex={3}><TextInput style={s.input} placeholder="Dallas" placeholderTextColor={PH} value={city} onChangeText={setCity} /></Field>
            <Field label="State" flex={1}><TextInput style={s.input} value={state} onChangeText={(t) => setState(t.toUpperCase())} autoCapitalize="characters" maxLength={2} /></Field>
          </View>

          <Pressable onPress={() => setMore((v) => !v)} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Icon name={more ? 'chevron-up' : 'chevron-down'} size={16} color={colors.accent} />
            <Text style={{ color: colors.accent, fontSize: 13, fontWeight: '600' }}>{more ? 'Hide extra details' : 'Extra details (stream, structure, height)'}</Text>
          </Pressable>
          {more ? (
            <View style={{ gap: space(2), padding: space(4), borderRadius: 12, backgroundColor: '#F8FAFF', borderWidth: 1, borderColor: colors.border }}>
              <Text style={{ fontSize: 12.5, fontWeight: '700', color: colors.text }}>Stream</Text>
              <Chips value={stream} onChange={setStream} options={STREAMS.map((k) => ({ key: k, label: k }))} />
              <Text style={{ fontSize: 12.5, fontWeight: '700', color: colors.text }}>Structure</Text>
              <Chips value={struct} onChange={setStruct} options={STRUCTS.map((k) => ({ key: k, label: k }))} />
              <View style={{ maxWidth: 200 }}><Field label="Height (ft)"><TextInput style={s.input} value={height} onChangeText={setHeight} keyboardType="numeric" /></Field></View>
            </View>
          ) : null}

          <Button title={busy ? 'Creating...' : 'Create site'} disabled={!valid || busy} onPress={create} />
        </View>
        {error ? <ErrorView error={error} /> : null}
        {created ? (
          <View style={{ flexDirection: 'row', gap: space(3), alignItems: 'center', marginTop: space(4), padding: space(3.5), borderRadius: 12, backgroundColor: '#F0FBF4', borderWidth: 1, borderColor: '#C6EBD3' }}>
            <Icon name="check-circle" size={22} color={colors.ok} />
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '800', color: colors.text }}>{created.id} is ready</Text>
              <Text style={{ fontSize: 12.5, color: '#3C6B4E' }}>SharePoint folder: {created.path}</Text>
            </View>
            <Button
              title="View in Sites"
              kind="secondary"
              small
              onPress={() => router.push('/(tabs)/sites')}
            />
          </View>
        ) : null}
      </Card>

      <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginTop: space(5), marginBottom: space(3) }}>
        <Text style={{ fontSize: 16, fontWeight: '800', color: colors.text }}>All sites</Text>
        <Muted>{sites.data?.sites.length ?? 0} in SharePoint</Muted>
      </View>
      {sites.error ? <ErrorView error={sites.error} onRetry={sites.reload} /> : null}
      {sites.data && sites.data.sites.length === 0 ? <Card><View style={{ alignItems: 'center', padding: space(4) }}><Icon name="folder" size={28} color="#B8C2D6" /><Muted style={{ marginTop: 6 }}>No sites yet. Create the first one above.</Muted></View></Card> : null}
      {sites.data?.sites.map((x) => (
        <Card key={x.site_id} style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), padding: space(3.5), marginBottom: space(2) }}>
          <IconBadge name="map-pin" size={38} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontWeight: '800', color: colors.text }}>{x.site_id}</Text>
            <Muted>{[x.site_name, [x.city, x.state].filter(Boolean).join(', ')].filter(Boolean).join(' · ')}</Muted>
          </View>
          {x.stream ? <Badge text={x.stream} color={colors.info} /> : null}
          <Badge text={`${x.files} file${x.files === 1 ? '' : 's'}`} color={x.files ? colors.ok : colors.muted} />
        </Card>
      ))}
      </>}
    </ScrollView>
  );
}
