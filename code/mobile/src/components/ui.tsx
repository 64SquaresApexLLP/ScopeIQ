// ScopeIQ component library: the building blocks every screen uses. Flat, technical, consistent.
import { Feather } from '@expo/vector-icons';
import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Animated, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, TextStyle, View, ViewStyle } from 'react-native';
import { ApiError } from '../lib/api';
import { settings } from '../lib/config';
import { colors, font, radius, shadow, shadowLift, shadowPopover, space, statusColor, tint, tintFor } from './theme';

export type IconName = React.ComponentProps<typeof Feather>['name'];

// ------------------------------------------------------------------ text
const ACRONYMS = new Set(['BOM', 'RFI', 'RFIS', 'RFDS', 'CD', 'CDS', 'MA', 'SA', 'AE', 'EHS', 'FBA', 'SP', 'CX', 'ID', 'PDF', 'DXF', 'CSV', 'QA', 'REV', 'URL', 'API']);
/** "IN_RECONCILIATION" -> "In reconciliation", "MA_SA" -> "MA SA"; mixed text and IDs are left as they are. */
export function humanize(t: string): string {
  if (!/^[A-Z_ ]+$/.test(t)) return t.replace(/_/g, ' ');
  const words = t.split(/[_ ]+/).filter(Boolean);
  return words.map((w, i) => (ACRONYMS.has(w) ? w : i === 0 ? w[0] + w.slice(1).toLowerCase() : w.toLowerCase())).join(' ');
}

export function Title({ children, style }: { children: React.ReactNode; style?: TextStyle }) {
  return <Text style={[s.title, style]}>{children}</Text>;
}
export function Muted({ children, style, numberOfLines }: { children: React.ReactNode; style?: TextStyle; numberOfLines?: number }) {
  return <Text style={[s.muted, style]} numberOfLines={numberOfLines}>{children}</Text>;
}
export function Body({ children, style, selectable }: { children: React.ReactNode; style?: TextStyle; selectable?: boolean }) {
  return <Text style={[s.body, style]} selectable={selectable}>{children}</Text>;
}
export function Mono({ children, style }: { children: React.ReactNode; style?: TextStyle }) {
  return <Text style={[{ fontFamily: font.mono, fontSize: 12.5, color: colors.text }, style]} selectable>{children}</Text>;
}

// ------------------------------------------------------------------ layout
export function Card({ children, style, onPress, padded = true }: { children: React.ReactNode; style?: ViewStyle | ViewStyle[]; onPress?: () => void; padded?: boolean }) {
  if (!onPress) return <View style={[s.card, !padded && { padding: 0 }, style as any]}>{children}</View>;
  return (
    <Pressable onPress={onPress} accessibilityRole="button"
      style={({ pressed, hovered }: any) => [s.card, !padded && { padding: 0 }, hovered && { borderColor: colors.borderStrong, ...shadowLift }, pressed && { opacity: 0.85 }, style as any]}>
      {children}
    </Pressable>
  );
}

export function Section({ title, subtitle, right, children, style }: { title: string; subtitle?: string; right?: React.ReactNode; children: React.ReactNode; style?: ViewStyle }) {
  return (
    <View style={[{ marginTop: space(5) }, style]}>
      <View style={s.sectionHead}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={s.sectionTitle}>{title}</Text>
          {subtitle ? <Text style={[s.muted, { marginTop: 2 }]}>{subtitle}</Text> : null}
        </View>
        {right}
      </View>
      {children}
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
      <Text style={s.kvVal} selectable>{v == null || v === '' ? '-' : v}</Text>
    </View>
  );
}

export function Divider({ style }: { style?: ViewStyle }) {
  return <View style={[{ height: 1, backgroundColor: colors.border, marginVertical: space(3) }, style]} />;
}

/** Page title block: optional eyebrow, title, description and right-aligned actions. */
export function PageHeader({ title, subtitle, eyebrow, actions, children }: { title: string; subtitle?: string; eyebrow?: string; actions?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <View style={{ marginBottom: space(5) }}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: space(4), flexWrap: 'wrap' }}>
        <View style={{ flexShrink: 1, minWidth: 240 }}>
          {eyebrow ? <Text style={s.eyebrow}>{eyebrow}</Text> : null}
          <Text style={s.pageTitle}>{title}</Text>
          {subtitle ? <Text style={[s.muted, { fontSize: 14, marginTop: 4, maxWidth: 720 }]}>{subtitle}</Text> : null}
        </View>
        {actions ? <View style={{ flexDirection: 'row', gap: space(2), alignItems: 'center', flexWrap: 'wrap' }}>{actions}</View> : null}
      </View>
      {children ? <View style={{ marginTop: space(4) }}>{children}</View> : null}
    </View>
  );
}
/** Kept for existing screens: now a plain page header (no banner). */
export function Hero({ title, subtitle, children }: { title: string; subtitle?: string; icon?: IconName; children?: React.ReactNode }) {
  return <PageHeader title={title} subtitle={subtitle}>{children}</PageHeader>;
}

// ------------------------------------------------------------------ status
export function Badge({ text, color, dot, style }: { text?: string | null; color?: string; dot?: boolean; style?: ViewStyle }) {
  if (!text) return null;
  const t = tintFor(color ?? statusColor(text));
  return (
    <View style={[s.badge, { backgroundColor: t.bg, borderColor: t.line }, style]}>
      {dot ? <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: t.fg }} /> : null}
      <Text style={[s.badgeText, { color: t.fg }]} numberOfLines={1}>{humanize(text)}</Text>
    </View>
  );
}
export const StatusBadge = (p: { text?: string | null; color?: string }) => <Badge {...p} dot />;

export function Banner({ kind = 'info', title, children, icon, action }: { kind?: keyof typeof tint; title?: string; children?: React.ReactNode; icon?: IconName; action?: React.ReactNode }) {
  const t = tint[kind];
  const ic: IconName = icon ?? (kind === 'danger' ? 'alert-octagon' : kind === 'warn' ? 'alert-triangle' : kind === 'ok' ? 'check-circle' : 'info');
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(3), padding: space(3.5), borderRadius: radius.lg, backgroundColor: t.bg, borderWidth: 1, borderColor: t.line, marginBottom: space(3), alignItems: 'flex-start' }}>
      <Feather name={ic} size={16} color={t.fg} style={{ marginTop: 1 }} />
      <View style={{ flex: 1, minWidth: 220, gap: 2 }}>
        {title ? <Text style={{ fontWeight: '600', color: t.fg, fontSize: 13.5 }}>{title}</Text> : null}
        {typeof children === 'string' ? <Text style={{ color: colors.text, fontSize: 13, lineHeight: 19 }}>{children}</Text> : children}
      </View>
      {action}
    </View>
  );
}

export function ProgressBar({ value, color = colors.accent, height = 6 }: { value: number; color?: string; height?: number }) {
  return (
    <View style={{ height, backgroundColor: colors.border, borderRadius: height, overflow: 'hidden' }}>
      <View style={{ height: '100%', width: `${Math.max(0, Math.min(100, value))}%`, backgroundColor: color, borderRadius: height }} />
    </View>
  );
}

// ------------------------------------------------------------------ actions
type BtnKind = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
export function Button({ title, onPress, kind = 'primary', disabled, small, icon, iconRight, style }: {
  title: string; onPress: () => void; kind?: BtnKind; disabled?: boolean; small?: boolean; icon?: IconName; iconRight?: IconName; style?: ViewStyle;
}) {
  const v = {
    primary: { bg: colors.accent, hover: colors.accentHover, fg: '#fff', line: colors.accent },
    danger: { bg: colors.danger, hover: '#B91C1C', fg: '#fff', line: colors.danger },
    secondary: { bg: '#fff', hover: colors.surfaceAlt, fg: colors.text, line: colors.borderStrong },
    outline: { bg: '#fff', hover: colors.surfaceAlt, fg: colors.text, line: colors.borderStrong },
    ghost: { bg: 'transparent', hover: colors.surfaceAlt, fg: colors.accent, line: 'transparent' },
  }[kind];
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button"
      style={({ pressed, hovered }: any) => [s.btn, small && s.btnSmall,
        { backgroundColor: hovered && !disabled ? v.hover : v.bg, borderColor: v.line, opacity: disabled ? 0.5 : pressed ? 0.9 : 1 },
        (kind === 'secondary' || kind === 'outline') && shadow, style]}>
      {icon ? <Feather name={icon} size={small ? 13 : 15} color={v.fg} /> : null}
      <Text style={[s.btnText, { color: v.fg }, small && { fontSize: 12.5 }]} numberOfLines={1}>{title}</Text>
      {iconRight ? <Feather name={iconRight} size={small ? 13 : 15} color={v.fg} /> : null}
    </Pressable>
  );
}

export function IconButton({ icon, onPress, label, color = colors.muted, danger }: { icon: IconName; onPress: () => void; label: string; color?: string; danger?: boolean }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label}
      style={({ hovered, pressed }: any) => ({ width: 30, height: 30, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center',
        backgroundColor: hovered ? (danger ? tint.danger.bg : colors.surfaceAlt) : 'transparent', opacity: pressed ? 0.7 : 1 })}>
      <Feather name={icon} size={15} color={danger ? colors.danger : color} />
    </Pressable>
  );
}

// ------------------------------------------------------------------ inputs
/** Filter pills (single choice). */
export function Chips<T extends string>({ options, value, onChange }: { options: { key: T; label: string; count?: number }[]; value: T; onChange: (v: T) => void }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space(1.5), paddingVertical: space(1) }}>
      {options.map((o) => {
        const on = value === o.key;
        return (
          <Pressable key={o.key} onPress={() => onChange(o.key)} accessibilityRole="tab" accessibilityState={{ selected: on }}
            style={({ hovered }: any) => [s.chip, on ? s.chipOn : hovered && { borderColor: colors.borderStrong, backgroundColor: colors.surfaceAlt }]}>
            <Text style={[s.chipText, on && { color: colors.accent }]}>{o.label}</Text>
            {o.count != null ? <Text style={[s.chipCount, on && { color: colors.accent, backgroundColor: '#fff' }]}>{o.count}</Text> : null}
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

export function SearchBox({ value, onChangeText, placeholder, style }: { value: string; onChangeText: (t: string) => void; placeholder?: string; style?: ViewStyle }) {
  const [focus, setFocus] = useState(false);
  return (
    <View style={[s.search, focus && s.inputFocus, style]}>
      <Feather name="search" size={15} color={colors.faint} />
      <TextInput value={value} onChangeText={onChangeText} placeholder={placeholder} placeholderTextColor={colors.faint}
        onFocus={() => setFocus(true)} onBlur={() => setFocus(false)} style={{ flex: 1, fontSize: 14, color: colors.text, paddingVertical: 0, outlineStyle: 'none' } as any} />
      {value ? <Pressable onPress={() => onChangeText('')} accessibilityLabel="Clear search"><Feather name="x" size={14} color={colors.muted} /></Pressable> : null}
    </View>
  );
}

/** Simple dropdown: a button that opens a list of options under it. */
export function Select<T extends string>({ value, options, onChange, placeholder = 'Select', width = 200 }: { value: T | null; options: { key: T; label: string }[]; onChange: (v: T) => void; placeholder?: string; width?: number }) {
  const [open, setOpen] = useState(false);
  const cur = options.find((o) => o.key === value);
  return (
    <View style={{ width, zIndex: open ? 50 : 1 }}>
      <Pressable onPress={() => setOpen((o) => !o)} accessibilityRole="button" style={({ hovered }: any) => [s.select, hovered && { borderColor: colors.borderStrong }]}>
        <Text style={{ flex: 1, fontSize: 13.5, color: cur ? colors.text : colors.faint }} numberOfLines={1}>{cur?.label ?? placeholder}</Text>
        <Feather name={open ? 'chevron-up' : 'chevron-down'} size={15} color={colors.muted} />
      </Pressable>
      {open ? (
        <View style={[s.menu, shadowPopover as any]}>
          {options.map((o) => (
            <Pressable key={o.key} onPress={() => { onChange(o.key); setOpen(false); }}
              style={({ hovered }: any) => [{ paddingHorizontal: space(3), paddingVertical: space(2.25), flexDirection: 'row', alignItems: 'center', gap: 8 }, hovered && { backgroundColor: colors.surfaceAlt }]}>
              <Text style={{ flex: 1, fontSize: 13.5, color: colors.text, fontWeight: o.key === value ? '600' : '400' }}>{o.label}</Text>
              {o.key === value ? <Feather name="check" size={14} color={colors.accent} /> : null}
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}

/** Segmented tab tokens (shared by every nested tab bar). */
export const segment = {
  track: '#EEF2F7', trackLine: '#E2E8F0', hover: 'rgba(15,23,42,0.05)',
  activeBg: '#FFFFFF', activeText: colors.navy, activeIcon: colors.accent, idle: '#64748B',
  radiusTrack: 10, radiusItem: 8, height: 34,
};
export interface TabItem<T extends string> { key: T; label: string; icon?: IconName; count?: number; accessibilityLabel?: string }

/** Segmented tabs: icon + short label items in one light-grey track. The active item is a white raised pill.
 *  Arrow keys move between tabs (web); the bar scrolls sideways when it does not fit. */
export function SegmentedTabs<T extends string>({ tabs, value, onChange, style }: { tabs: TabItem<T>[]; value: T; onChange: (v: T) => void; style?: ViewStyle }) {
  const keyNav = (e: any) => {
    const i = tabs.findIndex((t) => t.key === value);
    const step = e?.nativeEvent?.key === 'ArrowRight' ? 1 : e?.nativeEvent?.key === 'ArrowLeft' ? -1 : 0;
    if (!step || i < 0) return;
    e.preventDefault?.();
    onChange(tabs[(i + step + tabs.length) % tabs.length].key);
  };
  return (
    <View style={[{ flexDirection: 'row' }, style]}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0, maxWidth: '100%' }}>
        <View accessibilityRole="tablist" {...({ onKeyDown: keyNav } as any)}
          style={{ flexDirection: 'row', gap: 2, padding: 3, borderRadius: segment.radiusTrack, backgroundColor: segment.track, borderWidth: 1, borderColor: segment.trackLine }}>
          {tabs.map((t) => {
            const on = t.key === value;
            return (
              <Pressable key={t.key} onPress={() => onChange(t.key)} accessibilityRole="tab" accessibilityState={{ selected: on }}
                accessibilityLabel={t.accessibilityLabel ?? (t.count ? `${t.label}, ${t.count}` : t.label)}
                style={({ hovered, pressed }: any) => [{
                  flexDirection: 'row', alignItems: 'center', gap: 7, height: segment.height, paddingHorizontal: 12, borderRadius: segment.radiusItem,
                  backgroundColor: on ? segment.activeBg : hovered ? segment.hover : 'transparent', opacity: pressed ? 0.85 : 1,
                }, on && ({ boxShadow: '0 1px 2px rgba(16,24,40,0.08), 0 0 0 1px rgba(16,24,40,0.04)' } as any)]}>
                {t.icon ? <Feather name={t.icon} size={15} color={on ? segment.activeIcon : segment.idle} /> : null}
                <Text style={{ fontSize: 13, fontWeight: on ? '600' : '500', color: on ? segment.activeText : segment.idle }} numberOfLines={1}>{t.label}</Text>
                {t.count ? (
                  <View style={{ minWidth: 18, height: 18, paddingHorizontal: 5, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: on ? colors.soft : '#E2E8F0' }}>
                    <Text style={{ fontSize: 11, fontWeight: '600', color: on ? colors.accent : segment.idle }}>{t.count}</Text>
                  </View>
                ) : null}
              </Pressable>
            );
          })}
        </View>
      </ScrollView>
    </View>
  );
}
/** Nested tab bars across the app use the segmented style. */
export const Tabs = SegmentedTabs;

// ------------------------------------------------------------------ data display
export function Stat({ label, value, color, icon, hint, onPress }: { label: string; value: React.ReactNode; color?: string; icon?: IconName; hint?: string; onPress?: () => void }) {
  const body = (hovered = false) => (
    <View style={[s.stat, onPress && { flexBasis: 'auto', flexGrow: 1 }, hovered && { borderColor: colors.borderStrong, ...shadowLift }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space(2) }}>
        <Text style={s.statLabel} numberOfLines={1}>{label}</Text>
        {icon ? <Feather name={icon} size={15} color={colors.faint} /> : null}
      </View>
      <Text style={[s.statValue, color ? { color } : null]}>{value}</Text>
      {hint ? <Text style={[s.muted, { fontSize: 12, marginTop: 2 }]} numberOfLines={1}>{hint}</Text> : null}
    </View>
  );
  if (!onPress) return body();
  return <Pressable onPress={onPress} accessibilityRole="button" style={{ flexGrow: 1, flexBasis: 150 }}>{({ hovered }: any) => body(hovered)}</Pressable>;
}
export const KpiCard = Stat;

export interface Column<T> { key: string; title: string; flex?: number; width?: number; align?: 'left' | 'right' | 'center'; render?: (row: T) => React.ReactNode }
/** Readable data table: header row, hover rows, optional row press. Scrolls sideways when the screen is narrow. */
export function DataTable<T>({ columns, rows, keyFor, onRowPress, empty, minWidth = 720, dense }: {
  columns: Column<T>[]; rows: T[]; keyFor: (r: T, i: number) => string; onRowPress?: (r: T) => void; empty?: React.ReactNode; minWidth?: number; dense?: boolean;
}) {
  const cell = (c: Column<T>) => ({ flex: c.width ? undefined : c.flex ?? 1, width: c.width, flexShrink: c.width ? 0 : 1, minWidth: 0, overflow: 'hidden' as const,
    paddingHorizontal: space(3), justifyContent: 'center' as const,
    alignItems: c.align === 'right' ? 'flex-end' as const : c.align === 'center' ? 'center' as const : 'stretch' as const });
  const [boxW, setBoxW] = useState(0);
  return (
    <View style={[s.card, { padding: 0, overflow: 'hidden' }]} onLayout={(e) => setBoxW(e.nativeEvent.layout.width)}>
      <ScrollView horizontal showsHorizontalScrollIndicator={boxW < minWidth} contentContainerStyle={{ minWidth: '100%' as any }}>
        <View style={{ width: Math.max(minWidth, boxW - 2), flexGrow: 1 }}>
          <View style={s.th}>
            {columns.map((c) => <View key={c.key} style={cell(c)}><Text style={s.thText} numberOfLines={1}>{c.title}</Text></View>)}
          </View>
          {rows.length === 0 ? (empty ?? <Empty text="Nothing to show." />) : rows.map((r, i) => (
            <Pressable key={keyFor(r, i)} onPress={onRowPress ? () => onRowPress(r) : undefined} disabled={!onRowPress}
              style={({ hovered }: any) => [s.tr, dense && { minHeight: 40 }, i === rows.length - 1 && { borderBottomWidth: 0 }, hovered && onRowPress && { backgroundColor: colors.surfaceAlt }]}>
              {columns.map((c) => (
                <View key={c.key} style={cell(c)}>
                  {c.render ? c.render(r) : <Text style={s.td} numberOfLines={1}>{String((r as any)[c.key] ?? '-')}</Text>}
                </View>
              ))}
            </Pressable>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

/** One row of a list inside a card: icon tile, title, supporting text, meta line and a right-hand slot. */
export function ListItem({ icon, iconColor = colors.accent, title, subtitle, meta, right, onPress, dim, last }: {
  icon?: IconName; iconColor?: string; title: React.ReactNode; subtitle?: React.ReactNode; meta?: React.ReactNode; right?: React.ReactNode; onPress?: () => void; dim?: boolean; last?: boolean;
}) {
  const t = tintFor(iconColor);
  return (
    <Pressable onPress={onPress} disabled={!onPress} accessibilityRole={onPress ? 'button' : undefined}
      style={({ hovered }: any) => ({ flexDirection: 'row', gap: space(3), alignItems: 'flex-start', paddingHorizontal: space(4), paddingVertical: space(3.5),
        borderBottomWidth: last ? 0 : 1, borderBottomColor: colors.border, backgroundColor: hovered && onPress ? colors.surfaceAlt : 'transparent', opacity: dim ? 0.62 : 1 })}>
      {icon ? <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: t.bg, alignItems: 'center', justifyContent: 'center' }}><Feather name={icon} size={15} color={t.fg} /></View> : null}
      <View style={{ flex: 1, minWidth: 0, gap: 3 }}>
        {typeof title === 'string' ? <Text style={{ fontSize: 13.5, fontWeight: '600', color: colors.text }} numberOfLines={2}>{title}</Text> : title}
        {subtitle ? (typeof subtitle === 'string' ? <Text style={{ fontSize: 13, color: colors.text, lineHeight: 19 }} numberOfLines={3}>{subtitle}</Text> : subtitle) : null}
        {meta ? (typeof meta === 'string' ? <Text style={{ fontSize: 12, color: colors.faint }}>{meta}</Text> : meta) : null}
      </View>
      {right ? <View style={{ alignItems: 'flex-end', gap: 6 }}>{right}</View> : null}
      {onPress ? <Feather name="chevron-right" size={16} color={colors.faint} style={{ marginTop: 8 }} /> : null}
    </Pressable>
  );
}

export function Icon({ name, size = 18, color = colors.muted }: { name: IconName; size?: number; color?: string }) {
  return <Feather name={name} size={size} color={color} />;
}
/** Icon in a soft square tile. */
export function IconBadge({ name, color = colors.accent, size = 40 }: { name: IconName; color?: string; size?: number }) {
  const t = tintFor(color);
  return (
    <View style={{ width: size, height: size, borderRadius: Math.min(10, size / 3.5), backgroundColor: t.bg, alignItems: 'center', justifyContent: 'center' }}>
      <Feather name={name} size={size * 0.45} color={t.fg} />
    </View>
  );
}
export function Avatar({ name, size = 36, light }: { name?: string; size?: number; light?: boolean }) {
  const ini = (name ?? '?').split(/\s+/).map((w) => w[0]).filter(Boolean).slice(0, 2).join('').toUpperCase();
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, alignItems: 'center', justifyContent: 'center', backgroundColor: light ? '#E8EEF7' : colors.accent }}>
      <Text style={{ color: light ? colors.navy : '#fff', fontWeight: '600', fontSize: size * 0.36 }}>{ini}</Text>
    </View>
  );
}

// ------------------------------------------------------------------ feedback
export function Skeleton({ width = '100%', height = 14, r = radius.sm, style }: { width?: number | string; height?: number; r?: number; style?: ViewStyle }) {
  const o = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([Animated.timing(o, { toValue: 0.45, duration: 700, useNativeDriver: false }), Animated.timing(o, { toValue: 1, duration: 700, useNativeDriver: false })]));
    loop.start();
    return () => loop.stop();
  }, [o]);
  return <Animated.View style={[{ width: width as any, height, borderRadius: r, backgroundColor: '#E5EBF3', opacity: o }, style]} />;
}

/** Placeholder while data loads: a few skeleton rows inside a card. */
export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <View style={[s.card, { gap: space(3) }]} accessibilityLabel="Loading" accessibilityRole="progressbar">
      <Skeleton width="35%" height={16} />
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} width={`${90 - i * 12}%`} />)}
    </View>
  );
}
export function Spinner() {
  return <View style={s.center}><ActivityIndicator color={colors.accent} /></View>;
}

export function ErrorView({ error, onRetry }: { error: ApiError | Error; onRetry?: () => void }) {
  const e = error as ApiError;
  return (
    <Banner kind="danger" title={e.message || 'Something went wrong'}
      action={onRetry ? <Button small kind="secondary" title="Try again" icon="rotate-cw" onPress={onRetry} /> : undefined}>
      {e.code ? <Text style={{ color: colors.muted, fontSize: 12, fontFamily: font.mono }}>{`${e.code}${e.correlationId ? `  ·  ref ${e.correlationId}` : ''}`}</Text> : null}
    </Banner>
  );
}

export function EmptyState({ icon = 'inbox', title, text, action }: { icon?: IconName; title: string; text?: string; action?: React.ReactNode }) {
  return (
    <View style={{ alignItems: 'center', paddingVertical: space(10), paddingHorizontal: space(6) }}>
      <View style={{ width: 44, height: 44, borderRadius: 10, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }}>
        <Feather name={icon} size={20} color={colors.muted} />
      </View>
      <Text style={{ marginTop: space(3), fontSize: 15, fontWeight: '600', color: colors.text, textAlign: 'center' }}>{title}</Text>
      {text ? <Text style={[s.muted, { marginTop: 4, textAlign: 'center', maxWidth: 420 }]}>{text}</Text> : null}
      {action ? <View style={{ marginTop: space(4) }}>{action}</View> : null}
    </View>
  );
}
export function Empty({ text }: { text: string }) {
  return <EmptyState title={text} />;
}

export function EnvBanner() {
  if (!settings.showEnvBanner) return null;
  return <View style={s.banner}><Text style={s.bannerText}>{`${settings.env.toUpperCase()}  ·  ${settings.apiUrl}`}</Text></View>;
}

// ------------------------------------------------------------------ overlays
export function Dialog({ open, onClose, title, children, footer, width = 520 }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; footer?: React.ReactNode; width?: number }) {
  return (
    <Modal visible={open} transparent animationType="none" onRequestClose={onClose}>
      <Pressable onPress={onClose} style={{ flex: 1, backgroundColor: 'rgba(15,23,42,0.45)', alignItems: 'center', justifyContent: 'center', padding: space(4) }}>
        <Pressable onPress={() => undefined} style={[{ width: '100%', maxWidth: width, backgroundColor: '#fff', borderRadius: radius.xl, borderWidth: 1, borderColor: colors.border }, shadowPopover as any]}>
          <View style={{ flexDirection: 'row', alignItems: 'center', padding: space(5), paddingBottom: space(3) }}>
            <Text style={{ flex: 1, fontSize: 16, fontWeight: '600', color: colors.text }}>{title}</Text>
            <IconButton icon="x" label="Close" onPress={onClose} />
          </View>
          <View style={{ paddingHorizontal: space(5), paddingBottom: space(5) }}>{children}</View>
          {footer ? <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: space(2), padding: space(4), borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.surfaceAlt, borderBottomLeftRadius: radius.xl, borderBottomRightRadius: radius.xl }}>{footer}</View> : null}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

export function ConfirmDialog({ open, title, message, confirmText = 'Confirm', danger, onConfirm, onCancel }: { open: boolean; title: string; message: string; confirmText?: string; danger?: boolean; onConfirm: () => void; onCancel: () => void }) {
  return (
    <Dialog open={open} onClose={onCancel} title={title} width={440}
      footer={<><Button kind="secondary" small title="Cancel" onPress={onCancel} /><Button kind={danger ? 'danger' : 'primary'} small title={confirmText} onPress={onConfirm} /></>}>
      <Text style={[s.body, { color: colors.muted }]}>{message}</Text>
    </Dialog>
  );
}

// ------------------------------------------------------------------ styles
export const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: space(6), paddingBottom: space(14) },
  card: { backgroundColor: colors.card, borderRadius: radius.lg, padding: space(4), marginBottom: space(3), borderWidth: 1, borderColor: colors.border, ...shadow } as any,
  title: { fontSize: 15, fontWeight: '600', color: colors.text, letterSpacing: -0.1 },
  pageTitle: { fontSize: 22, fontWeight: '600', color: colors.text, letterSpacing: -0.3 },
  eyebrow: { fontSize: 12, fontWeight: '600', color: colors.accent, marginBottom: 4 },
  body: { fontSize: 14, color: colors.text, lineHeight: 21 },
  muted: { fontSize: 13, color: colors.muted, lineHeight: 19 },
  sectionHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: space(3), gap: space(3) },
  sectionTitle: { fontSize: 14, fontWeight: '600', color: colors.text, letterSpacing: -0.1 },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 5, borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: 7, paddingVertical: 2, alignSelf: 'flex-start' },
  badgeText: { fontSize: 11.5, fontWeight: '600' },
  row: { flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' },
  kv: { flexDirection: 'row', paddingVertical: 5, gap: space(3) },
  kvKey: { width: 140, color: colors.muted, fontSize: 13 },
  kvVal: { flex: 1, color: colors.text, fontSize: 13, fontWeight: '500' },
  btn: { flexDirection: 'row', gap: 7, paddingHorizontal: space(4), height: 38, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  btnSmall: { paddingHorizontal: space(3), height: 30, borderRadius: radius.sm + 1 },
  btnSecondary: {},
  btnText: { fontWeight: '600', fontSize: 13.5 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: space(3), height: 30, backgroundColor: colors.card },
  chipOn: { backgroundColor: colors.soft, borderColor: '#BFD3FB' },
  chipText: { color: colors.text, fontSize: 12.5, fontWeight: '500' },
  chipCount: { fontSize: 11, fontWeight: '600', color: colors.muted, backgroundColor: colors.surfaceAlt, borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1, overflow: 'hidden' },
  center: { padding: space(8), alignItems: 'center', justifyContent: 'center' },
  banner: { backgroundColor: '#0B1B33', paddingVertical: 3, alignItems: 'center' },
  bannerText: { fontSize: 10, color: '#8EA2C6', letterSpacing: 0.6 },
  stat: { flexGrow: 1, flexBasis: 150, backgroundColor: colors.card, borderRadius: radius.lg, padding: space(4), borderWidth: 1, borderColor: colors.border, ...shadow } as any,
  statValue: { fontSize: 26, fontWeight: '600', color: colors.text, letterSpacing: -0.6, marginTop: space(2) },
  statLabel: { fontSize: 12.5, color: colors.muted, fontWeight: '500', flexShrink: 1 },
  input: { borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, paddingHorizontal: space(3), height: 38, backgroundColor: '#fff', fontSize: 14, color: colors.text },
  inputFocus: { borderColor: colors.accent, boxShadow: '0 0 0 3px rgba(37,99,235,0.15)' } as any,
  search: { flexDirection: 'row', alignItems: 'center', gap: space(2), borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, paddingHorizontal: space(3), height: 38, backgroundColor: '#fff' },
  select: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, paddingHorizontal: space(3), height: 38, backgroundColor: '#fff' },
  menu: { position: 'absolute', top: 42, left: 0, right: 0, backgroundColor: '#fff', borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingVertical: 4, zIndex: 100 } as any,
  th: { flexDirection: 'row', height: 38, alignItems: 'center', backgroundColor: colors.surfaceAlt, borderBottomWidth: 1, borderBottomColor: colors.border },
  thText: { fontSize: 11.5, fontWeight: '600', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.4 },
  tr: { flexDirection: 'row', minHeight: 52, alignItems: 'stretch', borderBottomWidth: 1, borderBottomColor: colors.border, paddingVertical: space(2) },
  td: { fontSize: 13.5, color: colors.text },
});
