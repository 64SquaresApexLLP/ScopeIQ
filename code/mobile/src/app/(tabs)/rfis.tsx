// Main sidebar tab: Redlines & RFIs across all the sites this role may see.
import { router } from 'expo-router';
import React from 'react';
import { ScrollView, Text, View } from 'react-native';
import { RedlinesRfisWorkspace } from '../../components/redlines/Workspace';
import { colors, space } from '../../components/theme';
import { Button, IconBadge, Muted, PageHeader, s } from '../../components/ui';
import { useAuth } from '../../lib/auth';

export default function RfisScreen() {
  const { can, user } = useAuth();
  if (!can('ADMIN', 'AE_ENGINEER', 'SCOPER', 'REVIEWER', 'ERICSSON')) {
    return (
      <View style={[s.screen, { alignItems: 'center', justifyContent: 'center', padding: space(8) }]}>
        <IconBadge name="lock" color={colors.muted} size={56} />
        <Text style={{ fontWeight: '800', fontSize: 18, color: colors.text, marginTop: space(3) }}>Restricted access</Text>
        <Muted>Only authorized scoping, engineering, and admin team members can access the Redlines & RFIs tab.</Muted>
        <View style={{ marginTop: space(4) }}>
          <Button title="Go to Dashboard" onPress={() => router.replace('/(tabs)')} />
        </View>
      </View>
    );
  }
  return (
    <ScrollView style={s.screen} contentContainerStyle={[s.content, { maxWidth: 1440, width: '100%', alignSelf: 'center' }]}>
      <PageHeader title="Redlines & RFIs"
        subtitle={user?.role === 'AE_ENGINEER' ? 'The drawing corrections and questions sent to your firm.' : 'Drawing corrections with their drone evidence, and requests for information, across the sites.'} />
      <RedlinesRfisWorkspace />
    </ScrollView>
  );
}
