import { Tabs } from 'expo-router';
import React from 'react';
import { ColorValue, Text } from 'react-native';
import { colors } from '../../components/theme';
import { useAuth } from '../../lib/auth';

const icon = (glyph: string) => ({ color }: { color: ColorValue }) => <Text style={{ color, fontSize: 18 }}>{glyph}</Text>;

export default function TabsLayout() {
  const { user } = useAuth();
  return (
    <Tabs screenOptions={{ headerStyle: { backgroundColor: colors.primary }, headerTintColor: '#fff', tabBarActiveTintColor: colors.primary }}>
      <Tabs.Screen name="index" options={{ title: 'Dashboard', tabBarIcon: icon('▦') }} />
      <Tabs.Screen name="sites" options={{ title: 'Sites', tabBarIcon: icon('⌖') }} />
      <Tabs.Screen name="queue" options={{ title: user?.role === 'CX_SP' ? 'Handshake' : 'Work queue', tabBarIcon: icon('☰') }} />
      <Tabs.Screen name="inbox" options={{ title: 'Inbox', tabBarIcon: icon('✉') }} />
      <Tabs.Screen name="more" options={{ title: 'More', tabBarIcon: icon('⋯') }} />
    </Tabs>
  );
}
