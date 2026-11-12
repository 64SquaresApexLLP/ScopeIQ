// Modern horizontal top navbar for ScopeIQ web.
import { Feather } from '@expo/vector-icons';
import { router, usePathname } from 'expo-router';
import React, { useState } from 'react';
import { Pressable, Text, View, useWindowDimensions, Modal, TouchableOpacity, ScrollView } from 'react-native';
import { brandGradient, colors, shadow, space } from './theme';
import { Avatar, Icon } from './ui';
import { useAuth } from '../lib/auth';
import { roleLabel } from '../lib/format';

interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentProps<typeof Feather>['name'];
  label: string;
}

function useNavItems(): NavItem[] {
  const { user } = useAuth();
  const isAe = user?.role === 'AE_ENGINEER';
  const isAdmin = user?.role === 'ADMIN';

  const items: NavItem[] = [];
  if (!isAe) {
    items.push({ name: 'index', href: '/(tabs)', icon: 'grid', label: 'Dashboard' });
    items.push({ name: 'sites', href: '/(tabs)/sites', icon: 'map-pin', label: 'Sites' });
  }
  if (!isAe) {
    items.push({ name: 'queue', href: '/(tabs)/queue', icon: 'list', label: user?.role === 'CX_SP' ? 'Handshake' : 'Work Queue' });
  }
  if (isAdmin || isAe) {
    items.push({ name: 'rfis', href: '/(tabs)/rfis', icon: 'edit-3', label: 'Redlines & RFIs' });
  }
  if (!isAe) {
    items.push({ name: 'inbox', href: '/(tabs)/inbox', icon: 'inbox', label: 'Inbox' });
  }
  if (isAdmin || isAe) {
    items.push({ name: 'sharepoint', href: '/(tabs)/sharepoint', icon: 'upload-cloud', label: 'SharePoint' });
  }
  if (isAdmin) {
    items.push({ name: 'admin', href: '/(tabs)/admin', icon: 'settings', label: 'Admin' });
  }
  return items;
}

function NavLogo() {
  return (
    <Pressable onPress={() => router.replace('/(tabs)')} style={{ flexDirection: 'row', alignItems: 'center', gap: space(2.5) }}>
      <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.18)', alignItems: 'center', justifyContent: 'center' }}>
        <Feather name="layers" size={18} color="#fff" />
      </View>
      <Text style={{ color: '#fff', fontSize: 20, fontWeight: '900', letterSpacing: -0.6 }}>ScopeIQ</Text>
    </Pressable>
  );
}

function DesktopNav() {
  const items = useNavItems();
  const { user, logout } = useAuth();
  const pathname = usePathname();

  const isActive = (item: NavItem) => {
    if (item.name === 'index') return pathname === '/' || pathname === '/(tabs)' || pathname === '/(tabs)/index';
    return pathname.includes(item.name);
  };

  return (
    <View style={[
      { flexDirection: 'row', alignItems: 'center', height: 60, paddingHorizontal: space(6), gap: space(2) },
      brandGradient,
      { boxShadow: '0 2px 20px rgba(15,42,95,0.35)' } as any,
    ]}>
      {/* Logo */}
      <NavLogo />

      {/* Divider */}
      <View style={{ width: 1, height: 24, backgroundColor: 'rgba(255,255,255,0.2)', marginHorizontal: space(3) }} />

      {/* Nav items */}
      <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1, gap: space(1) }}>
        {items.map((item) => {
          const active = isActive(item);
          return (
            <Pressable
              key={item.name}
              onPress={() => router.replace(item.href as any)}
              accessibilityRole="button"
              style={({ pressed, hovered }: any) => [
                {
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: space(1.5),
                  paddingHorizontal: space(3),
                  paddingVertical: space(2),
                  borderRadius: 10,
                  backgroundColor: active
                    ? 'rgba(255,255,255,0.18)'
                    : hovered
                    ? 'rgba(255,255,255,0.10)'
                    : 'transparent',
                  opacity: pressed ? 0.75 : 1,
                  borderBottomWidth: active ? 2 : 0,
                  borderBottomColor: active ? '#A5B4FC' : 'transparent',
                  marginBottom: active ? -2 : 0,
                },
              ]}
            >
              <Feather name={item.icon} size={15} color={active ? '#fff' : 'rgba(255,255,255,0.72)'} />
              <Text style={{
                color: active ? '#fff' : 'rgba(255,255,255,0.72)',
                fontSize: 13.5,
                fontWeight: active ? '700' : '500',
                letterSpacing: 0.1,
              }}>
                {item.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {/* User chip */}
      {user ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2) }}>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={{ color: '#fff', fontSize: 13, fontWeight: '700' }}>{user.name || roleLabel(user.role)}</Text>
            <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 11 }}>{roleLabel(user.role)}</Text>
          </View>
          <Avatar name={user.name || roleLabel(user.role)} size={34} />
          <Pressable
            onPress={logout}
            accessibilityRole="button"
            accessibilityLabel="Sign out"
            style={({ pressed }: any) => ({
              padding: 7,
              borderRadius: 9,
              backgroundColor: 'rgba(255,255,255,0.14)',
              opacity: pressed ? 0.7 : 1,
            })}
          >
            <Feather name="log-out" size={15} color="#fff" />
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

function MobileNav() {
  const items = useNavItems();
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  const isActive = (item: NavItem) => {
    if (item.name === 'index') return pathname === '/' || pathname === '/(tabs)' || pathname === '/(tabs)/index';
    return pathname.includes(item.name);
  };

  const navigate = (href: string) => {
    setMenuOpen(false);
    router.replace(href as any);
  };

  return (
    <>
      {/* Mobile top bar */}
      <View style={[
        { flexDirection: 'row', alignItems: 'center', height: 56, paddingHorizontal: space(4), justifyContent: 'space-between' },
        brandGradient,
        { boxShadow: '0 2px 12px rgba(15,42,95,0.3)' } as any,
      ]}>
        <NavLogo />
        <Pressable onPress={() => setMenuOpen(true)} style={{ padding: 8 }}>
          <Feather name="menu" size={22} color="#fff" />
        </Pressable>
      </View>

      {/* Mobile drawer */}
      <Modal visible={menuOpen} transparent animationType="fade" onRequestClose={() => setMenuOpen(false)}>
        <TouchableOpacity style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)' }} activeOpacity={1} onPress={() => setMenuOpen(false)}>
          <View style={{ position: 'absolute', top: 0, right: 0, bottom: 0, width: 280, backgroundColor: '#fff', ...shadow as any }}>
            {/* Drawer header */}
            <View style={[{ padding: space(5), paddingTop: space(8) }, brandGradient]}>
              <NavLogo />
              {user ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2.5), marginTop: space(4) }}>
                  <Avatar name={user.name || roleLabel(user.role)} size={38} />
                  <View>
                    <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>{user.name || roleLabel(user.role)}</Text>
                    <Text style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12 }}>{roleLabel(user.role)}</Text>
                  </View>
                </View>
              ) : null}
            </View>

            {/* Nav items */}
            <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: space(3) }}>
              {items.map((item) => {
                const active = isActive(item);
                return (
                  <Pressable
                    key={item.name}
                    onPress={() => navigate(item.href)}
                    style={[
                      {
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: space(3),
                        paddingHorizontal: space(4),
                        paddingVertical: space(3.5),
                        borderRadius: 12,
                        marginBottom: space(1),
                        backgroundColor: active ? colors.soft : 'transparent',
                      },
                    ]}
                  >
                    <Feather name={item.icon} size={18} color={active ? colors.accent : colors.muted} />
                    <Text style={{ color: active ? colors.accent : colors.text, fontWeight: active ? '700' : '500', fontSize: 15 }}>
                      {item.label}
                    </Text>
                    {active && <View style={{ flex: 1, alignItems: 'flex-end' }}><View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.accent }} /></View>}
                  </Pressable>
                );
              })}
            </ScrollView>

            {/* Sign out */}
            <Pressable
              onPress={() => { setMenuOpen(false); logout(); }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), padding: space(5), borderTopWidth: 1, borderTopColor: colors.border }}
            >
              <Icon name="log-out" size={18} color={colors.muted} />
              <Text style={{ color: colors.muted, fontSize: 14, fontWeight: '600' }}>Sign out</Text>
            </Pressable>
          </View>
        </TouchableOpacity>
      </Modal>
    </>
  );
}

export function NavBar() {
  const { width } = useWindowDimensions();
  const wide = width >= 768;
  return wide ? <DesktopNav /> : <MobileNav />;
}
