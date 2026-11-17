// Landing / sign-in: a brand panel on the left and the role choice on the right. Roles marked password_required
// (SCOPER, AE_ENGINEER, CX_SP, ADMIN) open the username + password form inside the chosen role's card; any other role
// still signs in with its demo account. The token carries the role.
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { router } from 'expo-router';
import React, { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, TextInput, useWindowDimensions, View } from 'react-native';
import { colors, shadow, shadowLift, space } from '../components/theme';
import { Button, ErrorView, Icon, IconName, Skeleton, s } from '../components/ui';
import { ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { roleLabel } from '../lib/format';
import { useApi } from '../lib/useApi';

interface DemoUser { user_id: string; name: string; role: string; organisation: string; persona: string; password_required?: boolean }
type McIcon = React.ComponentProps<typeof MaterialCommunityIcons>['name'];

const PAGE_BG = '#F4F7FB';
const SKY = '#93C5FD';          // light blue used for accents on the navy panel
const web = (style: object) => style as any;   // web-only style keys (transitions, cursor)

const ROLES: { role: string; icon: McIcon; blurb: string }[] = [
  { role: 'SCOPER', icon: 'hard-hat', blurb: 'Upload documents, run the pipeline and review findings.' },
  { role: 'AE_ENGINEER', icon: 'math-compass', blurb: 'Review drawings, respond to RFIs and complete redlines in the work queue.' },
  { role: 'CX_SP', icon: 'handshake-outline', blurb: 'Review drawings and BOM, agree or request changes in the handshake.' },
  { role: 'ADMIN', icon: 'shield-account-outline', blurb: 'Create sites and manage the platform.' },
];

const FEATURES: { icon: IconName; title: string; text: string }[] = [
  { icon: 'file-text', title: 'Document Intelligence', text: 'Reads RFDS, drawings, structural reports and drone surveys.' },
  { icon: 'check-square', title: 'Engineering Validation', text: 'Rules catch conflicts before a crew climbs the tower.' },
  { icon: 'shield', title: 'Evidence and Review', text: 'Every result is traceable and approved by a person.' },
];

/** Very faint engineering grid, a few soft blue tones and a restrained tower-with-signal motif behind the brand copy. */
function BrandBackdrop({ compact }: { compact: boolean }) {
  const step = 44;
  const line = 'rgba(148,184,255,0.06)';
  const tower = compact ? 170 : 300;
  return (
    <View pointerEvents="none" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, overflow: 'hidden' }}>
      {Array.from({ length: 48 }, (_, i) => (
        <View key={`v${i}`} style={{ position: 'absolute', top: 0, bottom: 0, left: i * step, width: 1, backgroundColor: line }} />
      ))}
      {Array.from({ length: 36 }, (_, i) => (
        <View key={`h${i}`} style={{ position: 'absolute', left: 0, right: 0, top: i * step, height: 1, backgroundColor: line }} />
      ))}
      {/* soft blue tonal accents */}
      <View style={[{ position: 'absolute', width: 560, height: 560, borderRadius: 280, top: -300, left: -220, backgroundColor: 'rgba(37,99,235,0.16)' }, web({ filter: 'blur(90px)' })]} />
      <View style={[{ position: 'absolute', width: 460, height: 460, borderRadius: 230, bottom: -240, right: -140, backgroundColor: 'rgba(37,99,235,0.14)' }, web({ filter: 'blur(90px)' })]} />
      {/* tower with signal rings, bottom right */}
      <View style={{ position: 'absolute', right: compact ? -20 : 24, bottom: compact ? -24 : -8, alignItems: 'center' }}>
        {[1, 2, 3].map((k) => {
          const d = tower * 0.42 * k;
          return (
            <View key={k} style={{ position: 'absolute', top: tower * 0.12 - d / 2, left: tower / 2 - d / 2, width: d, height: d, borderRadius: d / 2,
              borderWidth: 1, borderColor: `rgba(147,197,253,${0.11 - k * 0.025})` }} />
          );
        })}
        <MaterialCommunityIcons name="transmission-tower" size={tower} color="rgba(255,255,255,0.05)" />
      </View>
    </View>
  );
}

function RoleCard({ icon, title, blurb, selected, busy, onPress, children }: {
  icon: McIcon; title: string; blurb: string; selected: boolean; busy: boolean; onPress: () => void; children?: React.ReactNode;
}) {
  const [hovered, setHovered] = useState(false);
  const active = selected || hovered;
  return (
    <View style={[{ backgroundColor: selected ? '#FAFCFF' : '#fff', borderRadius: 14, borderWidth: 1, marginBottom: space(3),
      borderColor: selected ? colors.accent : hovered ? colors.borderStrong : colors.border, overflow: 'hidden' },
      web({ transitionProperty: 'border-color, box-shadow, background-color', transitionDuration: '160ms' }),
      selected ? web({ boxShadow: '0 0 0 3px rgba(37,99,235,0.12), 0 4px 12px rgba(16,24,40,0.06)' }) : hovered ? shadowLift : shadow]}>
      <Pressable onPress={onPress} onHoverIn={() => setHovered(true)} onHoverOut={() => setHovered(false)} disabled={busy}
        accessibilityRole="button" accessibilityLabel={`${title}. ${blurb}`} accessibilityState={{ selected, expanded: selected, busy }}
        style={({ pressed }) => [{ flexDirection: 'row', alignItems: 'center', gap: space(3.5), paddingVertical: space(3.5), paddingHorizontal: space(4),
          opacity: pressed ? 0.88 : 1 }, web({ cursor: busy ? 'default' : 'pointer' })]}>
        <View style={[{ width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center',
          backgroundColor: selected ? colors.accent : '#EEF4FF', borderWidth: 1, borderColor: selected ? colors.accent : '#DBE7FE' },
          web({ transitionProperty: 'background-color', transitionDuration: '160ms' })]}>
          <MaterialCommunityIcons name={icon} size={22} color={selected ? '#fff' : colors.accent} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={{ fontWeight: '600', color: colors.text, fontSize: 15, letterSpacing: -0.1 }}>{title}</Text>
          <Text style={{ color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 2 }}>{blurb}</Text>
        </View>
        {busy ? <ActivityIndicator size="small" color={colors.accent} /> : (
          <View style={[{ width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: active ? '#EEF4FF' : 'transparent' },
            web({ transitionProperty: 'background-color', transitionDuration: '160ms' })]}>
            <Icon name={selected ? 'chevron-down' : 'arrow-right'} size={16} color={active ? colors.accent : colors.faint} />
          </View>
        )}
      </Pressable>
      {children}
    </View>
  );
}

export default function Login() {
  const { login } = useAuth();
  const { width } = useWindowDimensions();
  const split = width >= 768;              // two columns on desktop and tablet, stacked on phones
  const roomy = width >= 1200;
  const users = useApi<DemoUser[]>('/auth/users');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [chosen, setChosen] = useState<DemoUser | null>(null);   // role waiting for its username + password
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const pick = async (u: DemoUser) => {
    setError(null);
    if (u.password_required) {
      if (chosen?.role === u.role) { setChosen(null); return; }   // tapping the open role again closes its form
      setChosen(u);
      setUsername('');
      setPassword('');
      return;
    }
    setChosen(null);
    setBusy(u.user_id);
    try {
      await login({ userId: u.user_id });
      router.replace(u.role === 'AE_ENGINEER' ? '/(tabs)/rfis' : '/(tabs)');
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(null);
    }
  };

  const signIn = async () => {
    if (!chosen || !username.trim() || !password) return;
    setBusy(chosen.user_id);
    setError(null);
    try {
      await login({ username, password, role: chosen.role });
      router.replace(chosen.role === 'AE_ENGINEER' ? '/(tabs)/rfis' : '/(tabs)');
    } catch (e) {
      setError(e as ApiError);
      setPassword('');
    } finally {
      setBusy(null);
    }
  };

  const pad = roomy ? 64 : split ? 40 : 24;

  const brand = (
    <View style={{ flex: split ? 11 : undefined, backgroundColor: colors.navy, overflow: 'hidden' }}>
      <BrandBackdrop compact={!split} />
      <View style={{ flex: 1, padding: pad, paddingTop: split ? pad : 28, paddingBottom: split ? pad : 36, justifyContent: 'space-between', gap: split ? space(10) : space(7) }}>
        {/* brand */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3) }}>
          <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center' }}>
            <MaterialCommunityIcons name="radio-tower" size={22} color="#fff" />
          </View>
          <View style={{ flexShrink: 1 }}>
            <Text style={{ color: '#fff', fontSize: 20, fontWeight: '700', letterSpacing: -0.3 }}>ScopeIQ</Text>
            <Text style={{ color: 'rgba(191,214,255,0.72)', fontSize: 10.5, fontWeight: '600', letterSpacing: 1.4, marginTop: 1 }}>
              CELL-SITE SCOPING AND ENGINEERING OPERATIONS
            </Text>
          </View>
        </View>

        {/* headline + description */}
        <View style={{ maxWidth: 560 }}>
          <Text accessibilityRole="header" style={{ color: '#fff', fontSize: roomy ? 40 : split ? 32 : 26, fontWeight: '700',
            letterSpacing: roomy ? -1.1 : -0.8, lineHeight: roomy ? 48 : split ? 39 : 32 }}>
            Cell-site scoping and engineering operations.
          </Text>
          <Text style={{ color: SKY, fontSize: split ? 18 : 16, fontWeight: '600', marginTop: space(4), letterSpacing: -0.2 }}>
            Telecom site scoping, automated.
          </Text>
          <Text style={{ color: 'rgba(226,232,240,0.78)', fontSize: split ? 15 : 14, lineHeight: split ? 24 : 21, marginTop: space(2), maxWidth: 470 }}>
            From documents to a reviewed bill of materials, with every finding backed by evidence.
          </Text>
        </View>

        {/* feature highlights */}
        <View style={{ gap: split ? space(5) : space(4), maxWidth: 520 }}>
          {FEATURES.map((f) => (
            <View key={f.title} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: space(3.5) }}>
              <View style={{ width: 38, height: 38, borderRadius: 10, alignItems: 'center', justifyContent: 'center',
                backgroundColor: 'rgba(37,99,235,0.18)', borderWidth: 1, borderColor: 'rgba(147,197,253,0.22)' }}>
                <Icon name={f.icon} size={17} color={SKY} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: '#fff', fontSize: 14.5, fontWeight: '600' }}>{f.title}</Text>
                <Text style={{ color: 'rgba(203,213,225,0.78)', fontSize: 13.5, lineHeight: 20, marginTop: 2 }}>{f.text}</Text>
              </View>
            </View>
          ))}
        </View>
      </View>
    </View>
  );

  const roleUsers = ROLES.map((r) => ({ def: r, user: (users.data ?? []).find((u) => u.role === r.role) }))
    .filter((x): x is { def: (typeof ROLES)[number]; user: DemoUser } => !!x.user);

  const form = (
    <View style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingHorizontal: space(4), paddingTop: space(4), paddingBottom: space(4.5), gap: space(3.5) }}>
      <Text style={{ color: colors.muted, fontSize: 12.5 }}>Use the username and password your administrator gave you.</Text>
      <View>
        <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.text, marginBottom: 6 }}>Username</Text>
        <TextInput style={[s.input, { backgroundColor: '#fff' }]} value={username} onChangeText={setUsername} autoCapitalize="none" autoCorrect={false}
          autoComplete="username" onSubmitEditing={signIn} autoFocus accessibilityLabel="Username" />
      </View>
      <View>
        <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.text, marginBottom: 6 }}>Password</Text>
        <TextInput style={[s.input, { backgroundColor: '#fff' }]} value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none"
          autoCorrect={false} autoComplete="password" onSubmitEditing={signIn} accessibilityLabel="Password" />
      </View>
      {error ? <ErrorView error={error} /> : null}
      <Button title={busy ? 'Signing in...' : `Sign in as ${chosen ? roleLabel(chosen.role) : ''}`} icon="log-in"
        disabled={!username.trim() || !password || !!busy} onPress={signIn} />
    </View>
  );

  const panel = (
    <View style={{ width: '100%', maxWidth: 480, alignSelf: 'center', paddingHorizontal: split ? (roomy ? 48 : 32) : 16, paddingVertical: split ? 48 : 28 }}>
      <Text accessibilityRole="header" style={{ fontSize: split ? 28 : 24, fontWeight: '700', color: colors.text, letterSpacing: -0.6 }}>Welcome to ScopeIQ</Text>
      <Text style={{ color: colors.muted, fontSize: 14.5, marginTop: 6, marginBottom: space(7) }}>Choose your role to continue.</Text>
      {error && !chosen ? <View style={{ marginBottom: space(3) }}><ErrorView error={error} /></View> : null}
      {users.error ? <ErrorView error={users.error} onRetry={users.reload} /> : null}
      {users.loading && !users.data ? ROLES.map((r) => <Skeleton key={r.role} height={74} r={14} style={{ marginBottom: space(3) }} />) : null}
      {roleUsers.map(({ def, user }) => {
        const selected = chosen?.role === user.role;
        return (
          <RoleCard key={user.user_id} icon={def.icon} title={roleLabel(user.role)} blurb={def.blurb} selected={selected}
            busy={busy === user.user_id && !selected} onPress={() => pick(user)}>
            {selected ? form : null}
          </RoleCard>
        );
      })}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: space(4) }}>
        <Icon name="lock" size={13} color={colors.faint} />
        <Text style={{ color: colors.faint, fontSize: 12 }}>Access is limited to the sites and actions of your role.</Text>
      </View>
    </View>
  );

  return split ? (
    <View style={{ flex: 1, flexDirection: 'row', backgroundColor: PAGE_BG }}>
      {brand}
      <ScrollView style={{ flex: 9, backgroundColor: PAGE_BG }} contentContainerStyle={{ flexGrow: 1, justifyContent: 'center' }}>{panel}</ScrollView>
    </View>
  ) : (
    <ScrollView style={{ flex: 1, backgroundColor: PAGE_BG }}>{brand}{panel}</ScrollView>
  );
}
