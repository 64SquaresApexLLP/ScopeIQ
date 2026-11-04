import React from 'react';
import { ScrollView, View } from 'react-native';
import { Button, Card, KV, s, Title } from '../../components/ui';
import { useAuth } from '../../lib/auth';
import { roleLabel } from '../../lib/format';

export default function More() {
  const { user, logout } = useAuth();

  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content}>
      <Card>
        <Title>{user?.name || roleLabel(user?.role)}</Title>
        <KV k="Role" v={user?.role} />
        {user?.user_id ? <KV k="Username" v={user.user_id} /> : null}
        {user?.organisation ? <KV k="Organisation" v={user.organisation} /> : null}
        {user?.service_provider ? <KV k="Service Provider" v={user.service_provider} /> : null}
        {user?.persona ? <KV k="Persona" v={user.persona} /> : null}
      </Card>

      <View style={{ marginTop: 16 }}>
        <Button title="Sign out" kind="secondary" onPress={logout} />
      </View>
    </ScrollView>
  );
}
