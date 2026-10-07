// Small reusable building blocks shared by every screen.
import React from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextStyle, View, ViewStyle } from 'react-native';
import { ApiError } from '../lib/api';
import { settings } from '../lib/config';
import { colors, space, statusColor } from './theme';

export function Card({ children, style, onPress }: { children: React.ReactNode; style?: ViewStyle; onPress?: () => void }) {
  const body = <View style={[s.card, style]}>{children}</View>;
  return onPress ? (
    <Pressable onPress={onPress} style={({ pressed }) => (pressed ? { opacity: 0.7 } : undefined)} accessibilityRole="button">
      {body}
    </Pressable>
  ) : (
    body
  );
}

export function Title({ children, style }: { children: React.ReactNode; style?: TextStyle }) {
  return <Text style={[s.title, style]}>{children}</Text>;
}
export function Muted({ children, style, numberOfLines }: { children: React.ReactNode; style?: TextStyle; numberOfLines?: number }) {
  return (
    <Text style={[s.muted, style]} numberOfLines={numberOfLines}>
      {children}
    </Text>
  );
}
export function Body({ children, style, selectable }: { children: React.ReactNode; style?: TextStyle; selectable?: boolean }) {
  return (
    <Text style={[s.body, style]} selectable={selectable}>
      {children}
    </Text>
  );
}

export function Section({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <View style={{ marginTop: space(4) }}>
      <View style={s.sectionHead}>
        <Text style={s.sectionTitle}>{title}</Text>
        {right}
      </View>
      {children}
    </View>
  );
}

export function Badge({ text, color }: { text?: string | null; color?: string }) {
  if (!text) return null;
  const c = color ?? statusColor(text);
  return (
    <View style={[s.badge, { borderColor: c, backgroundColor: c + '18' }]}>
      <Text style={[s.badgeText, { color: c }]}>{text.replace(/_/g, ' ')}</Text>
    </View>
  );
}

export function Row({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[s.row, style]}>{children}</View>;
}

export function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <View style={s.kv}>
      <Text style={s.kvKey}>{k}</Text>
      <Text style={s.kvVal} selectable>
        {v == null || v === '' ? '-' : v}
      </Text>
    </View>
  );
}

export function Button({ title, onPress, kind = 'primary', disabled, small }: {
  title: string; onPress: () => void; kind?: 'primary' | 'secondary' | 'danger'; disabled?: boolean; small?: boolean;
}) {
  const bg = kind === 'primary' ? colors.primary : kind === 'danger' ? colors.danger : colors.card;
  const fg = kind === 'secondary' ? colors.primary : '#fff';
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      style={({ pressed }) => [s.btn, small && s.btnSmall, { backgroundColor: bg, opacity: disabled ? 0.4 : pressed ? 0.75 : 1 }, kind === 'secondary' && s.btnSecondary]}
    >
      <Text style={[s.btnText, { color: fg }, small && { fontSize: 13 }]}>{title}</Text>
    </Pressable>
  );
}

export function Chips<T extends string>({ options, value, onChange }: { options: { key: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space(2), paddingVertical: space(2) }}>
      {options.map((o) => (
        <Pressable key={o.key} onPress={() => onChange(o.key)} style={[s.chip, value === o.key && s.chipOn]} accessibilityRole="tab" accessibilityState={{ selected: value === o.key }}>
          <Text style={[s.chipText, value === o.key && { color: '#fff' }]}>{o.label}</Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}

export function Loading() {
  return (
    <View style={s.center}>
      <ActivityIndicator color={colors.primary} />
    </View>
  );
}

export function ErrorView({ error, onRetry }: { error: ApiError | Error; onRetry?: () => void }) {
  const e = error as ApiError;
  return (
    <Card style={{ borderColor: colors.danger }}>
      <Text style={{ color: colors.danger, fontWeight: '600' }}>{e.message}</Text>
      {e.code ? <Muted>{`${e.code}${e.correlationId ? ` - ref ${e.correlationId}` : ''}`}</Muted> : null}
      {onRetry ? <View style={{ marginTop: space(2) }}><Button small kind="secondary" title="Try again" onPress={onRetry} /></View> : null}
    </Card>
  );
}

export function Empty({ text }: { text: string }) {
  return <Muted style={{ textAlign: 'center', padding: space(6) }}>{text}</Muted>;
}

export function EnvBanner() {
  if (!settings.showEnvBanner) return null;
  return (
    <View style={s.banner}>
      <Text style={s.bannerText}>{`${settings.env.toUpperCase()} - ${settings.apiUrl}`}</Text>
    </View>
  );
}

export function Stat({ label, value, color }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <View style={s.stat}>
      <Text style={[s.statValue, color ? { color } : null]}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

export const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: space(4), paddingBottom: space(12) },
  card: { backgroundColor: colors.card, borderRadius: 10, padding: space(3), marginBottom: space(2), borderWidth: 1, borderColor: colors.border },
  title: { fontSize: 16, fontWeight: '700', color: colors.text },
  body: { fontSize: 14, color: colors.text, lineHeight: 20 },
  muted: { fontSize: 13, color: colors.muted },
  sectionHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: space(2) },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5 },
  badge: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2, alignSelf: 'flex-start' },
  badgeText: { fontSize: 11, fontWeight: '700' },
  row: { flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' },
  kv: { flexDirection: 'row', paddingVertical: 3 },
  kvKey: { width: 130, color: colors.muted, fontSize: 13 },
  kvVal: { flex: 1, color: colors.text, fontSize: 13 },
  btn: { paddingHorizontal: space(4), paddingVertical: space(3), borderRadius: 8, alignItems: 'center' },
  btnSmall: { paddingHorizontal: space(3), paddingVertical: space(2) },
  btnSecondary: { borderWidth: 1, borderColor: colors.primary },
  btnText: { fontWeight: '700', fontSize: 15 },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: space(3), paddingVertical: space(1.5), backgroundColor: colors.card },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.text, fontSize: 13, fontWeight: '600' },
  center: { padding: space(8), alignItems: 'center', justifyContent: 'center' },
  banner: { backgroundColor: '#FFF3CD', paddingVertical: 2, alignItems: 'center' },
  bannerText: { fontSize: 11, color: '#7A5B00' },
  stat: { flexGrow: 1, flexBasis: 90, backgroundColor: colors.card, borderRadius: 10, padding: space(3), borderWidth: 1, borderColor: colors.border },
  statValue: { fontSize: 22, fontWeight: '800', color: colors.primary },
  statLabel: { fontSize: 12, color: colors.muted, marginTop: 2 },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: space(3), backgroundColor: '#fff', fontSize: 14, color: colors.text },
});
