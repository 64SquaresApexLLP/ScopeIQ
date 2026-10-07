import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { View } from 'react-native';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { colors } from '../components/theme';
import { EnvBanner, Loading } from '../components/ui';
import { AuthProvider, useAuth } from '../lib/auth';

function RootStack() {
  const { user, ready } = useAuth();
  if (!ready) return <Loading />;
  return (
    <Stack screenOptions={{ headerStyle: { backgroundColor: colors.primary }, headerTintColor: '#fff', contentStyle: { backgroundColor: colors.bg } }}>
      <Stack.Protected guard={!!user}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="site/[id]" options={{ title: 'Site' }} />
        <Stack.Screen name="discrepancy/[id]" options={{ title: 'Discrepancy' }} />
        <Stack.Screen name="bom/[revId]" options={{ title: 'BOM revision' }} />
        <Stack.Screen name="upload/[siteId]" options={{ title: 'Upload document', presentation: 'modal' }} />
        <Stack.Screen name="audit" options={{ title: 'Audit trail' }} />
        <Stack.Screen name="reference" options={{ title: 'Reference data' }} />
        <Stack.Screen name="logs" options={{ title: 'Logs' }} />
      </Stack.Protected>
      <Stack.Protected guard={!user}>
        <Stack.Screen name="login" options={{ headerShown: false }} />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <View style={{ flex: 1 }}>
        <EnvBanner />
        <ErrorBoundary>
          <RootStack />
        </ErrorBoundary>
      </View>
      <StatusBar style="light" />
    </AuthProvider>
  );
}
