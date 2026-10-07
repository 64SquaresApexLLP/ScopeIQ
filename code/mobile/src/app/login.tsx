// Mock login: choose a persona. Any account works with the demo password; the token carries the role.
import React, { useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { colors, space } from '../components/theme';
import { Badge, Card, ErrorView, Loading, Muted, Row, s, Title } from '../components/ui';
import { ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { useApi } from '../lib/useApi';

interface DemoUser { user_id: string; name: string; role: string; organisation: string; persona: string }

export default function Login() {
  const { login } = useAuth();
  const users = useApi<DemoUser[]>('/auth/users');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const pick = async (u: DemoUser) => {
    setBusy(u.user_id);
    setError(null);
    try {
      await login(u.user_id);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(null);
    }
  };

  return (
    <ScrollView style={s.screen} contentContainerStyle={[s.content, { paddingTop: space(16) }]}>
      <Text style={{ fontSize: 30, fontWeight: '900', color: colors.primary }}>ScopeIQ</Text>
      <Muted style={{ marginBottom: space(6) }}>BOM, site design and deployment scoping. Sign in as a demo persona.</Muted>
      {error ? <ErrorView error={error} /> : null}
      {users.loading ? <Loading /> : users.error ? <ErrorView error={users.error} onRetry={users.reload} /> : null}
      {(users.data ?? []).map((u) => (
        <Card key={u.user_id} onPress={() => pick(u)} style={busy === u.user_id ? { opacity: 0.5 } : undefined}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Title>{u.name}</Title>
            <Badge text={u.role} color={colors.primary} />
          </Row>
          <Muted>{`${u.persona ?? ''} - ${u.organisation}`}</Muted>
          <View />
        </Card>
      ))}
    </ScrollView>
  );
}
