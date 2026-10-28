// Sign-in: choose a role. Roles marked password_required (SCOPER) then ask for the username + password the admin created;
// the other roles still sign in with a demo account. The token carries the role.
import { router } from 'expo-router';
import React, { useState } from 'react';
import { Pressable, ScrollView, Text, TextInput, useWindowDimensions, View } from 'react-native';
import { brandGradient, colors, shadow, space } from '../components/theme';
import { Avatar, Button, ErrorView, Icon, IconName, Loading, s } from '../components/ui';
import { ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { roleLabel } from '../lib/format';
import { useApi } from '../lib/useApi';

interface DemoUser { user_id: string; name: string; role: string; organisation: string; persona: string; password_required?: boolean }

const ROLES = [
  { role: 'SCOPER', blurb: 'Upload documents, run the pipeline and review findings' },
  { role: 'AE_ENGINEER', blurb: 'Review drawings, respond to RFIs and complete redlines in the work queue' },
  { role: 'ADMIN', blurb: 'Create sites and manage the platform' },
];

const POINTS: { icon: IconName; text: string }[] = [
  { icon: 'file-text', text: 'Reads RFDS, drawings, structural reports and drone surveys' },
  { icon: 'check-circle', text: 'Rules catch conflicts before a crew climbs the tower' },
  { icon: 'shield', text: 'Every result is traceable and approved by a person' },
];

export default function Login() {
  const { login } = useAuth();
  const { width } = useWindowDimensions();
  const wide = width >= 900;
  const users = useApi<DemoUser[]>('/auth/users');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [chosen, setChosen] = useState<DemoUser | null>(null);   // role waiting for its username + password
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const pick = async (u: DemoUser) => {
    setError(null);
    if (u.password_required) {
      setChosen(u);
      setUsername('');
      setPassword('');
      return;
    }
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
      await login({ username, password });
      router.replace(chosen.role === 'AE_ENGINEER' ? '/(tabs)/rfis' : '/(tabs)');
    } catch (e) {
      setError(e as ApiError);
      setPassword('');
    } finally {
      setBusy(null);
    }
  };

  const back = () => {
    setChosen(null);
    setError(null);
  };

  const brand = (
    <View style={[{ padding: space(wide ? 12 : 6), justifyContent: 'center', flex: wide ? 1 : undefined }, brandGradient]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), marginBottom: space(6) }}>
        <View style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.18)', alignItems: 'center', justifyContent: 'center' }}>
          <Icon name="layers" size={24} color="#fff" />
        </View>
        <Text style={{ color: '#fff', fontSize: 32, fontWeight: '900', letterSpacing: -1 }}>ScopeIQ</Text>
      </View>
      <Text style={{ color: '#fff', fontSize: wide ? 34 : 24, fontWeight: '800', letterSpacing: -0.8, lineHeight: wide ? 42 : 30 }}>Telecom site scoping, automated.</Text>
      <Text style={{ color: 'rgba(255,255,255,0.75)', fontSize: 15, marginTop: space(3), marginBottom: space(8), maxWidth: 440, lineHeight: 22 }}>
        From documents to a reviewed bill of materials, with every finding backed by evidence.
      </Text>
      <View style={{ gap: space(4) }}>
        {POINTS.map((p) => (
          <View key={p.text} style={{ flexDirection: 'row', alignItems: 'center', gap: space(3) }}>
            <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.14)', alignItems: 'center', justifyContent: 'center' }}>
              <Icon name={p.icon} size={16} color="#fff" />
            </View>
            <Text style={{ color: 'rgba(255,255,255,0.9)', fontSize: 14, flex: 1 }}>{p.text}</Text>
          </View>
        ))}
      </View>
    </View>
  );

  const credentials = chosen ? (
    <View style={{ padding: space(wide ? 12 : 5), paddingBottom: space(12), maxWidth: 560, width: '100%', alignSelf: 'center' }}>
      <Pressable onPress={back} accessibilityRole="button" style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: space(4) }}>
        <Icon name="chevron-left" size={16} color={colors.accent} />
        <Text style={{ color: colors.accent, fontSize: 13, fontWeight: '600' }}>Back to roles</Text>
      </Pressable>
      <Text style={{ fontSize: 26, fontWeight: '800', color: colors.text, letterSpacing: -0.6 }}>Sign in as {roleLabel(chosen.role)}</Text>
      <Text style={{ color: colors.muted, fontSize: 14, marginTop: 4, marginBottom: space(6) }}>Use the username and password your administrator gave you.</Text>
      <View style={{ gap: space(4) }}>
        <View>
          <Text style={{ fontSize: 12.5, fontWeight: '700', color: colors.text, marginBottom: 6 }}>Username</Text>
          <TextInput style={s.input} value={username} onChangeText={setUsername} autoCapitalize="none" autoCorrect={false} autoComplete="username"
            onSubmitEditing={signIn} autoFocus />
        </View>
        <View>
          <Text style={{ fontSize: 12.5, fontWeight: '700', color: colors.text, marginBottom: 6 }}>Password</Text>
          <TextInput style={s.input} value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" autoCorrect={false}
            autoComplete="password" onSubmitEditing={signIn} />
        </View>
        {error ? <ErrorView error={error} /> : null}
        <Button title={busy ? 'Signing in...' : 'Sign in'} disabled={!username.trim() || !password || !!busy} onPress={signIn} />
      </View>
    </View>
  ) : null;

  const body = credentials ?? (
    <View style={{ padding: space(wide ? 12 : 5), paddingBottom: space(12), maxWidth: 560, width: '100%', alignSelf: 'center' }}>
      <Text style={{ fontSize: 26, fontWeight: '800', color: colors.text, letterSpacing: -0.6 }}>Sign in</Text>
      <Text style={{ color: colors.muted, fontSize: 14, marginTop: 4, marginBottom: space(6) }}>Choose your role to continue.</Text>
      {error ? <ErrorView error={error} /> : null}
      {users.loading ? <Loading /> : users.error ? <ErrorView error={users.error} onRetry={users.reload} /> : null}
      {ROLES.map((r) => (users.data ?? []).find((u) => u.role === r.role)).filter((u): u is DemoUser => !!u).map((u) => (
        <Pressable key={u.user_id} onPress={() => pick(u)} accessibilityRole="button" style={({ pressed, hovered }: any) => [
          { flexDirection: 'row', alignItems: 'center', gap: space(3), backgroundColor: '#fff', borderRadius: 16, padding: space(3.5), marginBottom: space(2.5), borderWidth: 1, borderColor: hovered ? colors.accent : colors.border, opacity: busy === u.user_id ? 0.5 : pressed ? 0.85 : 1 },
          shadow as any]}>
          <Avatar name={roleLabel(u.role)} size={42} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontWeight: '700', color: colors.text, fontSize: 15 }}>{roleLabel(u.role)}</Text>
            <Text style={{ color: colors.muted, fontSize: 12.5 }}>{ROLES.find((r) => r.role === u.role)?.blurb}</Text>
          </View>
          <Icon name="chevron-right" size={18} color={colors.muted} />
        </Pressable>
      ))}
    </View>
  );

  return wide ? (
    <View style={{ flex: 1, flexDirection: 'row' }}>{brand}<ScrollView style={{ flex: 1, backgroundColor: colors.bg }}>{body}</ScrollView></View>
  ) : (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }}>{brand}{body}</ScrollView>
  );
}
