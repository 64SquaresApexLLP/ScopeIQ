// Small reusable building blocks shared by every screen.
import React from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextStyle, View, ViewStyle } from 'react-native';
import { ApiError } from '../lib/api';
import { settings } from '../lib/config';
import { Feather } from '@expo/vector-icons';
import { brandGradient, colors, shadow, space, statusColor } from './theme';

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
    <View style={[s.badge, { backgroundColor: c + '1A' }]}>
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
  const bg = kind === 'primary' ? colors.accent : kind === 'danger' ? colors.danger : colors.card;
  const fg = kind === 'secondary' ? colors.text : '#fff';
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      style={({ pressed }) => [s.btn, small && s.btnSmall, { backgroundColor: bg, opacity: disabled ? 0.45 : pressed ? 0.85 : 1 }, kind === 'primary' && !disabled && ({ boxShadow: '0 4px 14px rgba(79,107,255,0.35)' } as any), kind === 'secondary' && s.btnSecondary]}
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

export type IconName = React.ComponentProps<typeof Feather>['name'];
export function Icon({ name, size = 18, color = colors.muted }: { name: IconName; size?: number; color?: string }) {
  return <Feather name={name} size={size} color={color} />;
}
/** Icon inside a soft tinted circle. */
export function IconBadge({ name, color = colors.accent, size = 40 }: { name: IconName; color?: string; size?: number }) {
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2.4, backgroundColor: color + '1A', alignItems: 'center', justifyContent: 'center' }}>
      <Feather name={name} size={size * 0.46} color={color} />
    </View>
  );
}
export function Avatar({ name, size = 36 }: { name?: string; size?: number }) {
  const ini = (name ?? '?').split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase();
  return (
    <View style={[{ width: size, height: size, borderRadius: size / 2, alignItems: 'center', justifyContent: 'center' }, brandGradient]}>
      <Text style={{ color: '#fff', fontWeight: '800', fontSize: size * 0.38 }}>{ini}</Text>
    </View>
  );
}
/** Gradient banner at the top of a page. */
export function Hero({ title, subtitle, icon, children }: { title: string; subtitle?: string; icon?: IconName; children?: React.ReactNode }) {
  return (
    <View style={[{ borderRadius: 20, padding: space(5), marginBottom: space(4), overflow: 'hidden' }, brandGradient, { boxShadow: '0 10px 30px rgba(15,42,95,0.28)' } as any]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3) }}>
        {icon ? <View style={{ width: 46, height: 46, borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.16)', alignItems: 'center', justifyContent: 'center' }}><Feather name={icon} size={22} color="#fff" /></View> : null}
        <View style={{ flex: 1 }}>
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '800', letterSpacing: -0.4 }}>{title}</Text>
          {subtitle ? <Text style={{ color: 'rgba(255,255,255,0.78)', fontSize: 13, marginTop: 2 }}>{subtitle}</Text> : null}
        </View>
      </View>
      {children}
    </View>
  );
}

export function Stat({ label, value, color, icon }: { label: string; value: React.ReactNode; color?: string; icon?: IconName }) {
  return (
    <View style={s.stat}>
      {icon ? <View style={{ marginBottom: space(3) }}><IconBadge name={icon} color={color ?? colors.accent} size={36} /></View> : null}
      <Text style={[s.statValue, color ? { color } : null]}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

export const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: space(5), paddingBottom: space(14) },
  card: { backgroundColor: colors.card, borderRadius: 16, padding: space(4), marginBottom: space(3), borderWidth: 1, borderColor: colors.border, ...shadow } as any,
  title: { fontSize: 16, fontWeight: '700', color: colors.text, letterSpacing: -0.2 },
  body: { fontSize: 14, color: colors.text, lineHeight: 21 },
  muted: { fontSize: 13, color: colors.muted, lineHeight: 19 },
  sectionHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: space(3) },
  sectionTitle: { fontSize: 12, fontWeight: '800', color: colors.muted, textTransform: 'uppercase', letterSpacing: 1 },
  badge: { borderWidth: 0, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3, alignSelf: 'flex-start' },
  badgeText: { fontSize: 11, fontWeight: '700', letterSpacing: 0.2 },
  row: { flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' },
  kv: { flexDirection: 'row', paddingVertical: 4 },
  kvKey: { width: 130, color: colors.muted, fontSize: 13 },
  kvVal: { flex: 1, color: colors.text, fontSize: 13, fontWeight: '500' },
  btn: { paddingHorizontal: space(5), paddingVertical: space(3.5), borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  btnSmall: { paddingHorizontal: space(3.5), paddingVertical: space(2), borderRadius: 10 },
  btnSecondary: { borderWidth: 1.5, borderColor: colors.border },
  btnText: { fontWeight: '700', fontSize: 15, letterSpacing: 0.1 },
  chip: { borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: space(3.5), paddingVertical: space(2), backgroundColor: colors.card },
  chipOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  chipText: { color: colors.text, fontSize: 13, fontWeight: '600' },
  center: { padding: space(8), alignItems: 'center', justifyContent: 'center' },
  banner: { backgroundColor: '#0B1B3A', paddingVertical: 3, alignItems: 'center' },
  bannerText: { fontSize: 10, color: '#8EA2D6', letterSpacing: 0.6 },
  stat: { flexGrow: 1, flexBasis: 150, backgroundColor: colors.card, borderRadius: 16, padding: space(4), borderWidth: 1, borderColor: colors.border, ...shadow } as any,
  statValue: { fontSize: 28, fontWeight: '800', color: colors.primary, letterSpacing: -0.5 },
  statLabel: { fontSize: 12, color: colors.muted, marginTop: 2, fontWeight: '600' },
  input: { borderWidth: 1.5, borderColor: colors.border, borderRadius: 12, paddingHorizontal: space(3.5), paddingVertical: space(3), backgroundColor: '#fff', fontSize: 14, color: colors.text },
});
