// Admin: create a site. This creates its SharePoint folder and the site record; the site then appears for uploads.
import { router } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';
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

const US_STATES = new Set([
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
  'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT',
  'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
]);

interface GeoResult {
  city?: string;
  state?: string;
  state_name?: string;
  zip?: string;
  county?: string;
  display_name?: string;
  suggested_site_id?: string;
  site_id_prefix?: string;
  error?: string;
}

const STOP_WORDS = new Set(['AND', 'OF', 'THE', '&']);

export function extractTwoLetterCode(name: string): string {
  if (!name) return 'XX';
  const raw = name.trim();
  const cleanUpper = raw.replace(/[^A-Za-z0-9]/g, '').toUpperCase();

  // User explicit example: Una -> UA
  if (cleanUpper === 'UNA') {
    return 'UA';
  }

  // If already a 2-letter uppercase abbreviation (e.g. "HP", "TX", "NY")
  if (cleanUpper.length === 2 && raw === raw.toUpperCase()) {
    return cleanUpper;
  }

  const parts = raw.split(/[\s\-_/]+/).map((w) => w.replace(/[^A-Za-z0-9]/g, '')).filter(Boolean);
  let words = parts;
  if (words.length >= 3) {
    const meaningful = words.filter((w) => !STOP_WORDS.has(w.toUpperCase()));
    if (meaningful.length >= 2) {
      words = meaningful;
    }
  }

  if (words.length === 0) return 'XX';

  if (words.length >= 2) {
    // 2 or more words: first alphabet of first two words
    return (words[0][0] + words[1][0]).toUpperCase();
  } else {
    // 1 word: first two alphabets
    const w = words[0].toUpperCase();
    if (w.length >= 2) {
      return w.slice(0, 2);
    }
    return (w + 'X').slice(0, 2);
  }
}

export function generateSitePrefix(state: string, city: string): string {
  const s = extractTwoLetterCode(state);
  const c = extractTwoLetterCode(city);
  return `${s}${c}`.toUpperCase();
}

async function fetchReverseGeocode(latNum: number, lonNum: number): Promise<GeoResult> {
  // 1. Try ScopeIQ Backend reverse geocode API
  try {
    const res = await api.get<GeoResult>(`/admin/geocode/reverse?lat=${latNum}&lon=${lonNum}`);
    if (res && (res.city || res.state || res.state_name)) {
      const exactState = res.state_name || res.state || '';
      return {
        ...res,
        state: exactState,
        state_name: exactState,
      };
    }
  } catch (err) {
    log.warn('Backend geocode endpoint failed, attempting browser fallback', { error: String(err) });
  }

  // 2. Direct browser fallback via BigDataCloud client API
  try {
    const url = `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${latNum}&longitude=${lonNum}&localityLanguage=en`;
    const r = await fetch(url);
    if (r.ok) {
      const d = await r.json();
      const stateName = d.principalSubdivision || '';
      const stateCode = (d.principalSubdivisionCode || '').replace(/^[A-Z]+-/, '').toUpperCase();
      const exactState = stateName || stateCode;
      const city = d.city || d.locality || '';
      const prefix = generateSitePrefix(exactState, city);
      return {
        city,
        state: exactState,
        state_name: exactState,
        zip: d.postcode || '',
        suggested_site_id: prefix.length === 4 ? `${prefix}0001` : undefined,
        site_id_prefix: prefix,
        display_name: [city, exactState, d.countryName].filter(Boolean).join(', '),
      };
    }
  } catch (err) {
    log.warn('Fallback geocode failed', { error: String(err) });
  }

  return { error: 'Could not resolve location for coordinates' };
}

function Field({ label, hint, error, badge, children, flex = 1 }: { label: string; hint?: string; error?: string; badge?: string; children: React.ReactNode; flex?: number }) {
  return (
    <View style={{ flex, minWidth: 120 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <Text style={{ fontSize: 12.5, fontWeight: '700', color: colors.text }}>{label}</Text>
        {badge ? <Badge text={badge} color={colors.accent} /> : null}
      </View>
      {children}
      {error ? <Text style={{ fontSize: 12, color: colors.danger, marginTop: 4 }}>{error}</Text> : hint ? <Text style={{ fontSize: 12, color: colors.muted, marginTop: 4 }}>{hint}</Text> : null}
    </View>
  );
}

export default function Admin() {
  const { can } = useAuth();
  const sites = useApi<{ location: string; sites: R[] }>('/sharepoint/sites');
  const [siteId, setSiteId] = useState('');
  const [isAutoSiteId, setIsAutoSiteId] = useState(false);
  const [isUserEditedId, setIsUserEditedId] = useState(false);
  const [generatingId, setGeneratingId] = useState(false);
  const [name, setName] = useState('');
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [more, setMore] = useState(false);
  const [height, setHeight] = useState('');
  const [stream, setStream] = useState<(typeof STREAMS)[number]>('BOM');
  const [struct, setStruct] = useState<(typeof STRUCTS)[number]>('Monopole');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [created, setCreated] = useState<{ id: string; path: string; lat?: number | null; lon?: number | null } | null>(null);
  const [section, setSection] = useState<'sites' | 'logins'>('sites');

  // Geolocation state
  const [resolvingGeo, setResolvingGeo] = useState(false);
  const [geoFeedback, setGeoFeedback] = useState<{ message: string; isSuccess: boolean } | null>(null);
  const [isAutoSuggested, setIsAutoSuggested] = useState(false);
  const [gpsLoading, setGpsLoading] = useState(false);

  const fetchNextSiteId = async (st: string, ct: string) => {
    const sTrim = st.trim();
    const cTrim = ct.trim();
    if (!sTrim && !cTrim) return;
    setGeneratingId(true);
    try {
      const res = await api.get<{ site_id: string; prefix: string; sequence: number }>(
        `/admin/sites/next-id?state=${encodeURIComponent(sTrim)}&city=${encodeURIComponent(cTrim)}`
      );
      if (res && res.site_id) {
        setSiteId(res.site_id);
        setIsAutoSiteId(true);
      }
    } catch (err) {
      log.warn('Could not fetch next site id from backend, using fallback calculation', { error: String(err) });
      const pref = generateSitePrefix(sTrim, cTrim);
      if (pref.length === 4) {
        setSiteId(`${pref}0001`);
        setIsAutoSiteId(true);
      }
    } finally {
      setGeneratingId(false);
    }
  };

  // Debounced auto-generation of Site ID when City or State are typed manually
  useEffect(() => {
    if (isUserEditedId) return;
    const st = state.trim();
    const ct = city.trim();
    if (st.length >= 2 && ct.length >= 1) {
      const timer = setTimeout(() => {
        fetchNextSiteId(st, ct);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [state, city, isUserEditedId]);

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
  const stateVal = state.trim();
  const stateOk = stateVal.length >= 2;
  const latN = parseFloat(lat.trim());
  const lonN = parseFloat(lon.trim());
  const hasCoordinates = lat.trim() !== '' && lon.trim() !== '';
  const coordsValid = !hasCoordinates || (!isNaN(latN) && !isNaN(lonN) && latN >= -90 && latN <= 90 && lonN >= -180 && lonN <= 180);
  const valid = idOk && name.trim().length >= 2 && city.trim().length >= 1 && stateOk && coordsValid;

  // Debounced reverse geocoding when coordinates change
  useEffect(() => {
    if (!hasCoordinates) {
      setGeoFeedback(null);
      setIsAutoSuggested(false);
      return;
    }

    if (isNaN(latN) || isNaN(lonN) || latN < -90 || latN > 90 || lonN < -180 || lonN > 180) {
      setGeoFeedback({ message: 'Coordinates out of range (-90..90, -180..180)', isSuccess: false });
      return;
    }

    const timer = setTimeout(async () => {
      setResolvingGeo(true);
      try {
        const res = await fetchReverseGeocode(latN, lonN);
        const exactState = res.state_name || res.state || '';
        const exactCity = res.city || '';
        if (exactCity || exactState) {
          if (exactCity) setCity(exactCity);
          if (exactState) setState(exactState);
          setIsAutoSuggested(true);

          // Auto-generate Site ID if user hasn't typed a custom one
          if (!isUserEditedId) {
            if (res.suggested_site_id) {
              setSiteId(res.suggested_site_id);
              setIsAutoSiteId(true);
            } else if (exactState || exactCity) {
              fetchNextSiteId(exactState, exactCity);
            }
          }

          const details = [exactCity, exactState, res.zip].filter(Boolean).join(', ');
          setGeoFeedback({
            message: `📍 Geolocation resolved: ${details}${res.county && res.county !== exactCity ? ` (${res.county})` : ''}`,
            isSuccess: true,
          });
        } else {
          setGeoFeedback({ message: 'No address found for these coordinates; enter City & State manually.', isSuccess: false });
        }
      } catch (e) {
        log.warn('Reverse geocode error', { error: String(e) });
        setGeoFeedback({ message: 'Could not contact reverse geocoder; please enter City & State manually.', isSuccess: false });
      } finally {
        setResolvingGeo(false);
      }
    }, 600);

    return () => clearTimeout(timer);
  }, [lat, lon]);

  const useCurrentGps = () => {
    if (typeof navigator !== 'undefined' && navigator.geolocation) {
      setGpsLoading(true);
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setGpsLoading(false);
          const curLat = pos.coords.latitude.toFixed(5);
          const curLon = pos.coords.longitude.toFixed(5);
          setLat(curLat);
          setLon(curLon);
        },
        (err) => {
          setGpsLoading(false);
          log.warn('GPS location failed', { error: err.message });
          alert('Could not get GPS location: ' + err.message);
        },
        { enableHighAccuracy: true, timeout: 8000 }
      );
    } else {
      alert('Geolocation is not supported in this browser/device.');
    }
  };

  const create = async () => {
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const res = await api.post<R>('/admin/sites', {
        site_id: siteId,
        site_name: name.trim(),
        latitude: lat ? Number(lat) : null,
        longitude: lon ? Number(lon) : null,
        city: city.trim(),
        state: state.trim(),
        stream,
        structure_type: struct,
        height_ft: height ? Number(height) : null,
      });
      setCreated({
        id: res.site.SITE_ID,
        path: res.sharepoint.path,
        lat: res.site.LATITUDE,
        lon: res.site.LONGITUDE,
      });
      log.info(`created site ${siteId} with location ${city}, ${state.trim()}`);
      setSiteId('');
      setName('');
      setLat('');
      setLon('');
      setCity('');
      setState('');
      setHeight('');
      setGeoFeedback(null);
      setIsAutoSuggested(false);
      setIsAutoSiteId(false);
      setIsUserEditedId(false);
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
      <Hero icon="settings" title="Create a site" subtitle="Adds the site with geolocation and its SharePoint folder so documents can be uploaded." />

      <Card style={{ padding: space(5) }}>
        <View style={{ gap: space(4) }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(4) }}>
            <Field
              label="Site ID"
              badge={isAutoSiteId ? 'Auto-generated' : undefined}
              hint={
                isAutoSiteId
                  ? `Auto-generated: ${extractTwoLetterCode(state)}${extractTwoLetterCode(city)} + sequence`
                  : '4 letters + 4 digits (e.g. HPUA0001, TXDA1024)'
              }
              error={siteId && !idOk ? 'Use 4 letters then 4 digits, e.g. HPUA0001' : undefined}
            >
              <View style={{ flexDirection: 'row', gap: space(2), alignItems: 'center' }}>
                <TextInput
                  style={[s.input, { flex: 1 }]}
                  placeholder="HPUA0001"
                  placeholderTextColor={PH}
                  value={siteId}
                  onChangeText={(t) => {
                    setSiteId(t.toUpperCase());
                    setIsUserEditedId(true);
                    setIsAutoSiteId(false);
                  }}
                  autoCapitalize="characters"
                  maxLength={8}
                />
                {generatingId ? (
                  <ActivityIndicator size="small" color={colors.accent} style={{ paddingHorizontal: 6 }} />
                ) : (city.trim() || state.trim()) ? (
                  <Pressable
                    onPress={() => {
                      setIsUserEditedId(false);
                      fetchNextSiteId(state, city);
                    }}
                    style={({ pressed }) => ({
                      paddingHorizontal: 10,
                      paddingVertical: 9,
                      borderRadius: 8,
                      backgroundColor: '#EBF2FF',
                      borderWidth: 1,
                      borderColor: '#C6D9FA',
                      opacity: pressed ? 0.7 : 1,
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 4,
                    })}
                    accessibilityLabel="Regenerate Site ID"
                  >
                    <Icon name="refresh-cw" size={12} color={colors.accent} />
                    <Text style={{ fontSize: 11.5, fontWeight: '700', color: colors.accent }}>Auto ID</Text>
                  </Pressable>
                ) : null}
              </View>
            </Field>
            <Field label="Site name" flex={2}>
              <TextInput style={s.input} placeholder="Lakewood Heights" placeholderTextColor={PH} value={name} onChangeText={setName} />
            </Field>
          </View>

          {/* Coordinates & Geolocation Section */}
          <View style={{ padding: space(3.5), borderRadius: 12, backgroundColor: '#F6F8FC', borderWidth: 1, borderColor: '#DCE3F0', gap: space(2.5) }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Icon name="map-pin" size={16} color={colors.accent} />
                <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }}>Coordinates & Geolocation</Text>
              </View>
              <Pressable
                onPress={useCurrentGps}
                disabled={gpsLoading}
                style={({ pressed }) => ({
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 5,
                  paddingHorizontal: 10,
                  paddingVertical: 5,
                  borderRadius: 6,
                  backgroundColor: '#EBF2FF',
                  opacity: pressed || gpsLoading ? 0.7 : 1,
                })}
              >
                {gpsLoading ? <ActivityIndicator size="small" color={colors.accent} /> : <Icon name="navigation" size={13} color={colors.accent} />}
                <Text style={{ fontSize: 12, fontWeight: '700', color: colors.accent }}>{gpsLoading ? 'Detecting...' : 'Use My GPS'}</Text>
              </Pressable>
            </View>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(3) }}>
              <Field label="Latitude" hint="e.g. 32.8341" error={lat && (isNaN(latN) || latN < -90 || latN > 90) ? 'Must be between -90 and 90' : undefined}>
                <TextInput
                  style={s.input}
                  placeholder="32.8341"
                  placeholderTextColor={PH}
                  value={lat}
                  onChangeText={setLat}
                  keyboardType="numeric"
                />
              </Field>
              <Field label="Longitude" hint="e.g. -96.7512" error={lon && (isNaN(lonN) || lonN < -180 || lonN > 180) ? 'Must be between -180 and 180' : undefined}>
                <TextInput
                  style={s.input}
                  placeholder="-96.7512"
                  placeholderTextColor={PH}
                  value={lon}
                  onChangeText={setLon}
                  keyboardType="numeric"
                />
              </Field>
            </View>

            {resolvingGeo ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 2 }}>
                <ActivityIndicator size="small" color={colors.accent} />
                <Text style={{ fontSize: 12.5, color: colors.accent, fontWeight: '600' }}>Resolving City & State from coordinates...</Text>
              </View>
            ) : geoFeedback ? (
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 8,
                  padding: 8,
                  borderRadius: 8,
                  backgroundColor: geoFeedback.isSuccess ? '#EAF8EE' : '#FFF5EB',
                  borderWidth: 1,
                  borderColor: geoFeedback.isSuccess ? '#BDE8C6' : '#FFDFB8',
                }}
              >
                <Icon name={geoFeedback.isSuccess ? 'check-circle' : 'alert-circle'} size={15} color={geoFeedback.isSuccess ? colors.ok : '#D97706'} />
                <Text style={{ fontSize: 12, color: geoFeedback.isSuccess ? '#24663B' : '#92400E', flex: 1, fontWeight: '600' }}>
                  {geoFeedback.message}
                </Text>
              </View>
            ) : (
              <Muted style={{ fontSize: 11.5 }}>
                Enter tower latitude and longitude to automatically reverse-geocode and suggest City and State.
              </Muted>
            )}
          </View>

          {/* City and State Inputs (Auto-suggested from Geolocation) */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(4) }}>
            <Field
              label="City"
              flex={3}
              badge={isAutoSuggested ? 'Suggested' : undefined}
              hint={isAutoSuggested ? 'Auto-suggested from coordinates (editable)' : 'City location'}
            >
              <TextInput
                style={s.input}
                placeholder="Dallas"
                placeholderTextColor={PH}
                value={city}
                onChangeText={(t) => {
                  setCity(t);
                  setIsAutoSuggested(false);
                }}
              />
            </Field>
            <Field
              label="State"
              flex={2}
              badge={isAutoSuggested ? 'Suggested' : undefined}
              hint={isAutoSuggested ? 'Auto-suggested from coordinates (editable)' : 'State or province'}
              error={state && !stateOk ? 'State name is required (min 2 characters)' : undefined}
            >
              <TextInput
                style={s.input}
                placeholder="State or Province (e.g. Himachal Pradesh, Texas)"
                placeholderTextColor={PH}
                value={state}
                onChangeText={(t) => {
                  setState(t);
                  setIsAutoSuggested(false);
                }}
                autoCapitalize="words"
              />
            </Field>
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
              <Text style={{ fontSize: 12.5, color: '#3C6B4E' }}>
                SharePoint folder: {created.path}
                {created.lat && created.lon ? ` · GPS: ${created.lat}, ${created.lon}` : ''}
              </Text>
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
