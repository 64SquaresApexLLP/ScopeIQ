// Admin: create the usernames + passwords Scopers, A&E Engineers and Service Providers sign in with, and disable / enable them.
// Stored in the local database (CORE.USER_LOGIN) as a salted hash; the password is never shown again after it is created.
// A Service Provider login belongs to one registered service provider and only ever sees that provider's sites.
import React, { useState } from 'react';
import { Text, TextInput, View } from 'react-native';
import { getLogger } from '../../lib/logger';
import { api, ApiError } from '../../lib/api';
import { roleLabel } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, space } from '../theme';
import { Badge, Button, Card, Chips, ErrorView, Hero, Icon, IconBadge, Muted, s } from '../ui';

const log = getLogger('admin.logins');
const PH = '#A9B3C2';
const MIN_PASSWORD = 8;
const ROLES = ['SCOPER', 'AE_ENGINEER', 'CX_SP'] as const;   // roles that sign in with a password (auth.password_roles)

function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: React.ReactNode }) {
  return (
    <View style={{ flex: 1, minWidth: 160 }}>
      <Text style={{ fontSize: 12.5, fontWeight: '700', color: colors.text, marginBottom: 6 }}>{label}</Text>
      {children}
      {error ? <Text style={{ fontSize: 12, color: colors.danger, marginTop: 4 }}>{error}</Text> : hint ? <Text style={{ fontSize: 12, color: colors.muted, marginTop: 4 }}>{hint}</Text> : null}
    </View>
  );
}

export function ScoperLogins() {
  const logins = useApi<R[]>('/admin/logins');
  const providers = useApi<{ user_id: string; name: string; market?: string }[]>('/sites/service-providers');
  const providerNames = Array.from(new Set((providers.data ?? []).map((p) => p.name).filter(Boolean))).sort();
  const [provider, setProvider] = useState<string>('');
  const [role, setRole] = useState<(typeof ROLES)[number]>('SCOPER');
  const [username, setUsername] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  const userOk = /^[A-Za-z0-9._-]{3,40}$/.test(username);
  const isSp = role === 'CX_SP';
  const valid = userOk && name.trim().length >= 2 && password.length >= MIN_PASSWORD && (!isSp || !!provider);

  const create = async () => {
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const res = await api.post<R>('/admin/logins', { username, display_name: name.trim(), password, role, ...(isSp ? { service_provider: provider } : {}) });
      setCreated(res.USERNAME);
      log.info(`created login ${res.USERNAME}`);
      setUsername(''); setName(''); setPassword('');
      logins.reload();
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };

  const setActive = async (x: R, active: boolean) => {
    setError(null);
    try {
      await api.patch(`/admin/logins/${encodeURIComponent(x.USERNAME)}`, { active });
      logins.reload();
    } catch (e) {
      setError(e as ApiError);
    }
  };

  return (
    <View>
      <Hero icon="users" title="User logins" subtitle="Create the username and password a Scoper, A&E Engineer or Service Provider signs in with." />

      <Card style={{ padding: space(5) }}>
        <View style={{ gap: space(4) }}>
          <View>
            <Text style={{ fontSize: 12.5, fontWeight: '700', color: colors.text, marginBottom: 6 }}>Role</Text>
            <Chips value={role} onChange={setRole} options={ROLES.map((r) => ({ key: r, label: roleLabel(r) }))} />
          </View>
          {isSp ? (
            <View>
              <Text style={{ fontSize: 12.5, fontWeight: '700', color: colors.text, marginBottom: 6 }}>Service provider</Text>
              {providers.error ? <ErrorView error={providers.error} onRetry={providers.reload} /> : providerNames.length === 0 ? (
                <Muted>{providers.loading ? 'Loading service providers...' : 'No service providers are registered.'}</Muted>
              ) : (
                <Chips value={provider} onChange={setProvider} options={providerNames.map((n) => ({ key: n, label: n }))} />
              )}
              <Text style={{ fontSize: 12, color: colors.muted, marginTop: 4 }}>This login only sees the sites assigned to the chosen service provider.</Text>
            </View>
          ) : null}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(4) }}>
            <Field label="Username" hint="Letters, digits, dot, dash or underscore" error={username && !userOk ? 'Use 3-40 letters, digits, . _ or -' : undefined}>
              <TextInput style={s.input} placeholder="asha.rao" placeholderTextColor={PH} value={username} onChangeText={setUsername}
                autoCapitalize="none" autoCorrect={false} maxLength={40} />
            </Field>
            <Field label="Name">
              <TextInput style={s.input} placeholder="Asha Rao" placeholderTextColor={PH} value={name} onChangeText={setName} />
            </Field>
          </View>
          <Field label="Password" hint={`At least ${MIN_PASSWORD} characters. Share it with the person privately.`}
            error={password && password.length < MIN_PASSWORD ? `At least ${MIN_PASSWORD} characters` : undefined}>
            <TextInput style={s.input} value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" autoCorrect={false} />
          </Field>
          <Button title={busy ? 'Creating...' : 'Create login'} disabled={!valid || busy} onPress={create} />
        </View>
        {error ? <ErrorView error={error} /> : null}
        {created ? (
          <View style={{ flexDirection: 'row', gap: space(3), alignItems: 'center', marginTop: space(4), padding: space(3.5), borderRadius: 12, backgroundColor: '#F0FBF4', borderWidth: 1, borderColor: '#C6EBD3' }}>
            <Icon name="check-circle" size={22} color={colors.ok} />
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '800', color: colors.text }}>Login {created} is ready</Text>
              <Text style={{ fontSize: 12.5, color: '#3C6B4E' }}>The password is not shown again. Share it with the person now.</Text>
            </View>
          </View>
        ) : null}
      </Card>

      <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginTop: space(5), marginBottom: space(3) }}>
        <Text style={{ fontSize: 16, fontWeight: '800', color: colors.text }}>All logins</Text>
        <Muted>{logins.data?.length ?? 0} created</Muted>
      </View>
      {logins.error ? <ErrorView error={logins.error} onRetry={logins.reload} /> : null}
      {logins.data && logins.data.length === 0 ? (
        <Card><View style={{ alignItems: 'center', padding: space(4) }}><Icon name="user-plus" size={28} color="#B8C2D6" /><Muted style={{ marginTop: 6 }}>No logins yet. Create the first one above.</Muted></View></Card>
      ) : null}
      {logins.data?.map((x) => (
        <Card key={x.USERNAME} style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), padding: space(3.5), marginBottom: space(2) }}>
          <IconBadge name="user" size={38} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontWeight: '800', color: colors.text }}>{x.USERNAME}</Text>
            <Muted>{[x.DISPLAY_NAME, roleLabel(x.ROLE_CODE), x.ROLE_CODE === 'CX_SP' ? x.ORGANISATION : null].filter(Boolean).join(' · ')}</Muted>
          </View>
          <Badge text={x.ACTIVE ? 'Active' : 'Disabled'} color={x.ACTIVE ? colors.ok : colors.muted} />
          {x.ROLE_CODE === 'ADMIN' ? null : (
            <Button small kind="secondary" title={x.ACTIVE ? 'Disable' : 'Enable'} onPress={() => setActive(x, !x.ACTIVE)} />
          )}
        </Card>
      ))}
    </View>
  );
}
