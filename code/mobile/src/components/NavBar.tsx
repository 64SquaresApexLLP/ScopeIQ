// Application shell: navy sidebar (logo + role-filtered navigation), a top bar with breadcrumb, page title,
// notifications and the signed-in user, and the page content. Below 900 px the sidebar becomes a drawer.
import { Feather } from '@expo/vector-icons';
import { router, usePathname } from 'expo-router';
import React, { useState } from 'react';
import { Modal, Pressable, ScrollView, Text, View, useWindowDimensions } from 'react-native';
import { useAuth } from '../lib/auth';
import { clean, roleLabel } from '../lib/format';
import { useApi } from '../lib/useApi';
import { colors, radius, shadowPopover, space } from './theme';
import { Avatar } from './ui';

type IconName = React.ComponentProps<typeof Feather>['name'];
interface NavItem { name: string; href: string; icon: IconName; label: string }
export interface Crumb { label: string; href?: string }

/** The screens this role may open. Same rules as before the redesign; nothing extra is exposed. */
function useNavItems(): NavItem[] {
  const { user } = useAuth();
  const isAe = user?.role === 'AE_ENGINEER';
  const isAdmin = user?.role === 'ADMIN';
  const items: NavItem[] = [];
  if (user?.role === 'CX_SP') {
    items.push({ name: 'index', href: '/(tabs)', icon: 'map-pin', label: 'Sites' });
    items.push({ name: 'inbox', href: '/(tabs)/inbox', icon: 'inbox', label: 'Inbox' });
    return items;
  }
  if (!isAe) {
    items.push({ name: 'index', href: '/(tabs)', icon: 'grid', label: 'Dashboard' });
    items.push({ name: 'sites', href: '/(tabs)/sites', icon: 'map-pin', label: 'Sites' });
    items.push({ name: 'queue', href: '/(tabs)/queue', icon: 'list', label: user?.role === 'CX_SP' ? 'Handshake' : 'Work Queue' });
  }
  if (isAe) items.push({ name: 'sites', href: '/(tabs)/sites', icon: 'map-pin', label: 'Sites' });
  if (isAdmin || isAe) items.push({ name: 'rfis', href: '/(tabs)/rfis', icon: 'edit-3', label: 'Redlines & RFIs' });
  if (!isAe) items.push({ name: 'inbox', href: '/(tabs)/inbox', icon: 'inbox', label: 'Inbox' });
  if (isAdmin || isAe) items.push({ name: 'sharepoint', href: '/(tabs)/sharepoint', icon: 'upload-cloud', label: 'SharePoint' });
  if (isAdmin) items.push({ name: 'admin', href: '/(tabs)/admin', icon: 'settings', label: 'Admin' });
  return items;
}

function isActive(item: NavItem, pathname: string) {
  if (item.name === 'index') return pathname === '/' || pathname === '/(tabs)' || pathname === '/index' || (item.label === 'Sites' && pathname.startsWith('/site/'));
  if (item.name === 'sites' && pathname.startsWith('/site/')) return true;
  return pathname === `/${item.name}` || pathname.startsWith(`/${item.name}/`);
}

function useCrumbs(override?: Crumb[]): Crumb[] {
  const pathname = usePathname();
  const items = useNavItems();
  if (override) return override;
  if (pathname === '/more') return [{ label: 'Profile' }];
  const hit = items.find((i) => isActive(i, pathname));
  return [{ label: hit?.label ?? 'ScopeIQ' }];
}

function Logo({ compact }: { compact?: boolean }) {
  return (
    <Pressable onPress={() => router.replace('/(tabs)')} accessibilityRole="button" accessibilityLabel="ScopeIQ home" style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
      <View style={{ width: 30, height: 30, borderRadius: 7, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center' }}>
        <Feather name="radio" size={16} color="#fff" />
      </View>
      {!compact ? (
        <View>
          <Text style={{ color: '#fff', fontSize: 16, fontWeight: '600', letterSpacing: -0.2 }}>ScopeIQ</Text>
          <Text style={{ color: 'rgba(203,213,225,0.7)', fontSize: 10.5, fontWeight: '500', letterSpacing: 0.3 }}>Cell-site scoping</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const items = useNavItems();
  const pathname = usePathname();
  return (
    <View style={{ gap: 2 }}>
      <Text style={{ color: 'rgba(148,163,184,0.85)', fontSize: 10.5, fontWeight: '600', letterSpacing: 0.8, textTransform: 'uppercase', paddingHorizontal: space(3), marginBottom: space(2) }}>Workspace</Text>
      {items.map((item) => {
        const on = isActive(item, pathname);
        return (
          <Pressable key={item.name} onPress={() => { onNavigate?.(); router.replace(item.href as any); }} accessibilityRole="link" accessibilityState={{ selected: on }}
            style={({ hovered, pressed }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, height: 36, paddingHorizontal: space(3), borderRadius: radius.md,
              backgroundColor: on ? colors.navy2 : hovered ? 'rgba(255,255,255,0.05)' : 'transparent', opacity: pressed ? 0.85 : 1 })}>
            {on ? <View style={{ position: 'absolute', left: 0, top: 9, bottom: 9, width: 3, borderRadius: 2, backgroundColor: '#60A5FA' }} /> : null}
            <Feather name={item.icon} size={16} color={on ? '#fff' : 'rgba(203,213,225,0.75)'} />
            <Text style={{ color: on ? '#fff' : 'rgba(226,232,240,0.82)', fontSize: 13.5, fontWeight: on ? '600' : '500' }}>{item.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function SidebarFooter() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <View style={{ borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.08)', paddingTop: space(3), paddingHorizontal: space(2), flexDirection: 'row', alignItems: 'center', gap: 10 }}>
      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: '#34D399' }} />
      <Text style={{ color: 'rgba(203,213,225,0.75)', fontSize: 12 }} numberOfLines={1}>Connected to ScopeIQ API</Text>
    </View>
  );
}

function Bell() {
  const { user } = useAuth();
  const canInbox = user?.role !== 'AE_ENGINEER';
  const inbox = useApi<any[]>(canInbox ? '/workflow/inbox?limit=99' : null);
  if (!canInbox) return null;
  const n = inbox.data?.length ?? 0;
  return (
    <Pressable onPress={() => router.replace('/(tabs)/inbox')} accessibilityRole="button" accessibilityLabel={`Notifications, ${n} unread`}
      style={({ hovered }: any) => ({ width: 36, height: 36, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: hovered ? colors.surfaceAlt : 'transparent' })}>
      <Feather name="bell" size={17} color={colors.muted} />
      {n > 0 ? (
        <View style={{ position: 'absolute', top: 2, left: 19, minWidth: 18, height: 16, paddingHorizontal: 4, borderRadius: 8, backgroundColor: colors.danger, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: '#fff' }}>
          <Text style={{ color: '#fff', fontSize: 9, fontWeight: '700' }}>{n > 99 ? '99+' : n}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

function UserMenu({ compact }: { compact?: boolean }) {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  if (!user) return null;
  const name = user.name || roleLabel(user.role);
  return (
    <View style={{ zIndex: 20 }}>
      <Pressable onPress={() => setOpen((o) => !o)} accessibilityRole="button" accessibilityLabel="Account menu"
        style={({ hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, paddingLeft: 6, paddingRight: 8, height: 40, borderRadius: radius.md, backgroundColor: hovered || open ? colors.surfaceAlt : 'transparent' })}>
        <Avatar name={name} size={30} />
        {!compact ? (
          <View>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '600' }} numberOfLines={1}>{name}</Text>
            <Text style={{ color: colors.muted, fontSize: 11.5 }}>{roleLabel(user.role)}</Text>
          </View>
        ) : null}
        <Feather name="chevron-down" size={14} color={colors.muted} />
      </Pressable>
      {open ? (
        <View style={[{ position: 'absolute', right: 0, top: 46, width: 220, backgroundColor: '#fff', borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingVertical: 6 }, shadowPopover as any]}>
          <View style={{ paddingHorizontal: space(3), paddingVertical: space(2), borderBottomWidth: 1, borderBottomColor: colors.border, marginBottom: 4 }}>
            <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{name}</Text>
            <Text style={{ fontSize: 12, color: colors.muted }}>{clean(user.organisation) || roleLabel(user.role)}</Text>
          </View>
          {[{ icon: 'user' as IconName, label: 'Profile', go: () => router.replace('/(tabs)/more') }, { icon: 'log-out' as IconName, label: 'Sign out', go: () => void logout() }].map((m) => (
            <Pressable key={m.label} onPress={() => { setOpen(false); m.go(); }} style={({ hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: space(3), height: 34, backgroundColor: hovered ? colors.surfaceAlt : 'transparent' })}>
              <Feather name={m.icon} size={15} color={colors.muted} />
              <Text style={{ fontSize: 13.5, color: colors.text }}>{m.label}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function TopBar({ crumbs, onMenu, narrow }: { crumbs: Crumb[]; onMenu?: () => void; narrow: boolean }) {
  const title = crumbs[crumbs.length - 1]?.label ?? '';
  return (
    <View style={{ height: 60, flexDirection: 'row', alignItems: 'center', gap: space(3), paddingHorizontal: narrow ? space(3) : space(6), backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: colors.border, zIndex: 10 }}>
      {onMenu ? (
        <Pressable onPress={onMenu} accessibilityRole="button" accessibilityLabel="Open navigation" style={{ width: 36, height: 36, alignItems: 'center', justifyContent: 'center' }}>
          <Feather name="menu" size={20} color={colors.text} />
        </Pressable>
      ) : null}
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, display: narrow && crumbs.length < 2 ? 'none' : 'flex' }}>
          {!narrow ? <Text style={{ fontSize: 12, color: colors.faint }}>ScopeIQ</Text> : null}
          {crumbs.map((c, i) => (
            <React.Fragment key={`${c.label}-${i}`}>
              {!narrow || i > 0 ? <Feather name="chevron-right" size={12} color={colors.faint} /> : null}
              {c.href && i < crumbs.length - 1 ? (
                <Pressable onPress={() => router.replace(c.href as any)}><Text style={{ fontSize: 12, color: colors.muted }}>{c.label}</Text></Pressable>
              ) : (
                <Text style={{ fontSize: 12, color: i === crumbs.length - 1 ? colors.text : colors.muted, fontWeight: i === crumbs.length - 1 ? '500' : '400' }} numberOfLines={1}>{c.label}</Text>
              )}
            </React.Fragment>
          ))}
        </View>
        <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text, letterSpacing: -0.2, marginTop: 1 }} numberOfLines={1}>{title}</Text>
      </View>
      <Bell />
      <View style={{ width: 1, height: 24, backgroundColor: colors.border }} />
      <UserMenu compact={narrow} />
    </View>
  );
}

/** Wraps a page with the sidebar and the top bar. `crumbs` overrides the breadcrumb (for detail pages). */
export function AppShell({ children, crumbs }: { children: React.ReactNode; crumbs?: Crumb[] }) {
  const { width } = useWindowDimensions();
  const narrow = width < 900;
  const [drawer, setDrawer] = useState(false);
  const trail = useCrumbs(crumbs);

  const sidebar = (onNavigate?: () => void) => (
    <View style={{ width: 236, backgroundColor: colors.navy, paddingHorizontal: space(3), paddingTop: space(5), paddingBottom: space(4), flex: narrow ? 1 : undefined }}>
      <View style={{ paddingHorizontal: space(2), marginBottom: space(7) }}><Logo /></View>
      <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}><SidebarNav onNavigate={onNavigate} /></ScrollView>
      <SidebarFooter />
    </View>
  );

  return (
    <View style={{ flex: 1, flexDirection: 'row', backgroundColor: colors.bg }}>
      {!narrow ? sidebar() : null}
      <View style={{ flex: 1, minWidth: 0 }}>
        <TopBar crumbs={trail} narrow={narrow} onMenu={narrow ? () => setDrawer(true) : undefined} />
        <View style={{ flex: 1 }}>{children}</View>
      </View>
      {narrow ? (
        <Modal visible={drawer} transparent animationType="none" onRequestClose={() => setDrawer(false)}>
          <View style={{ flex: 1, flexDirection: 'row' }}>
            <View style={{ width: 260 }}>{sidebar(() => setDrawer(false))}</View>
            <Pressable style={{ flex: 1, backgroundColor: 'rgba(15,23,42,0.45)' }} onPress={() => setDrawer(false)} accessibilityLabel="Close navigation" />
          </View>
        </Modal>
      ) : null}
    </View>
  );
}
