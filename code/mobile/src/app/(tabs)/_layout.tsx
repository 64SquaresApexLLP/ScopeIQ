import { Feather } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import React from 'react';
import { ColorValue, Pressable, Text, useWindowDimensions, View } from 'react-native';
import { colors, space } from '../../components/theme';
import { Avatar } from '../../components/ui';
import { useAuth } from '../../lib/auth';
import { roleLabel } from '../../lib/format';

const icon = (name: React.ComponentProps<typeof Feather>['name']) => ({ color, size }: { color: ColorValue; size: number }) => <Feather name={name} size={size - 2} color={color as string} />;

function UserChip() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), marginRight: space(4) }}>
      <View style={{ alignItems: 'flex-end' }}>
        <Text style={{ color: '#fff', fontSize: 13, fontWeight: '700' }}>{user.name || roleLabel(user.role)}</Text>
        <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 11 }}>{roleLabel(user.role)}</Text>
      </View>
      <Avatar name={user.name || roleLabel(user.role)} size={34} />
      <Pressable
        onPress={logout}
        accessibilityRole="button"
        accessibilityLabel="Sign out"
        style={({ pressed }) => ({
          marginLeft: 4,
          padding: 6,
          borderRadius: 8,
          backgroundColor: 'rgba(255,255,255,0.18)',
          opacity: pressed ? 0.7 : 1,
        })}
      >
        <Feather name="log-out" size={14} color="#fff" />
      </Pressable>
    </View>
  );
}

export default function TabsLayout() {
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  const wide = width >= 900;
  const isAe = user?.role === 'AE_ENGINEER';

  return (
    <Tabs
      initialRouteName={isAe ? 'rfis' : 'index'}
      screenOptions={{
        headerStyle: { backgroundColor: colors.primary, height: 64, shadowOpacity: 0, borderBottomWidth: 0 } as any,
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: '800', fontSize: 18, letterSpacing: -0.3 },
        headerRight: () => <UserChip />,
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontSize: wide ? 12 : 10.5, fontWeight: '700' },
        tabBarPosition: wide ? 'left' : 'bottom',
        tabBarVariant: 'uikit',
        tabBarLabelPosition: wide ? 'beside-icon' : 'below-icon',
        tabBarStyle: wide
          ? ({ backgroundColor: '#fff', borderRightWidth: 1, borderRightColor: colors.border, paddingTop: space(3) } as any)
          : ({ backgroundColor: '#fff', borderTopColor: colors.border, height: 62, paddingBottom: 6, paddingTop: 6 } as any),
        tabBarActiveBackgroundColor: wide ? colors.soft : undefined,
      } as any}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Dashboard',
          tabBarLabel: wide ? 'Dashboard' : 'Home',
          tabBarIcon: icon('grid'),
          href: isAe ? null : undefined,
        }}
      />
      <Tabs.Screen
        name="sites"
        options={{
          title: 'Sites',
          tabBarIcon: icon('map-pin'),
        }}
      />
      <Tabs.Screen
        name="queue"
        options={{
          title: user?.role === 'CX_SP' ? 'Handshake' : 'Work queue',
          tabBarLabel: wide ? undefined : 'Queue',
          tabBarIcon: icon('list'),
        }}
      />
      <Tabs.Screen
        name="rfis"
        options={{
          title: 'Redlines & RFIs',
          tabBarLabel: wide ? 'Redlines & RFIs' : 'Redlines & RFIs',
          tabBarIcon: icon('edit-3'),
          href: user?.role === 'ADMIN' || isAe ? undefined : null,
        }}
      />
      <Tabs.Screen
        name="inbox"
        options={{
          title: 'Inbox',
          tabBarIcon: icon('inbox'),
        }}
      />
      <Tabs.Screen
        name="sharepoint"
        options={{
          title: 'SharePoint',
          tabBarLabel: wide ? 'SharePoint' : 'Files',
          tabBarIcon: icon('upload-cloud'),
          href: user?.role === 'ADMIN' || isAe ? undefined : null,
        }}
      />
      <Tabs.Screen
        name="admin"
        options={{
          title: 'Admin',
          tabBarIcon: icon('settings'),
          href: user?.role === 'ADMIN' ? undefined : null,
        }}
      />
      <Tabs.Screen
        name="more"
        options={{
          title: 'More',
          tabBarIcon: icon('more-horizontal'),
          href: isAe ? null : undefined,
        }}
      />
    </Tabs>
  );
}
