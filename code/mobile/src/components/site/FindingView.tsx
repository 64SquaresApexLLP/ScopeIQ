// How a finding (discrepancy) looks: severity accent, a plain title, where it is, what was expected vs found,
// and what to do about it. Shared by the Discrepancies tab, the stage 3 list and the finding page.
import { router } from 'expo-router';
import React from 'react';
import { Pressable, Text, View } from 'react-native';
import { SECTOR, show } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { colors, shadow, space } from '../theme';
import { Badge, Icon, IconBadge, IconName } from '../ui';

export const SEV: Record<string, { color: string; label: string; icon: IconName }> = {
  CRITICAL: { color: colors.red, label: 'Critical', icon: 'alert-octagon' },
  HIGH: { color: colors.danger, label: 'High', icon: 'alert-triangle' },
  MEDIUM: { color: colors.warn, label: 'Medium', icon: 'alert-circle' },
  LOW: { color: colors.info, label: 'Low', icon: 'info' },
};
export const OUTCOME: Record<string, { label: string; icon: IconName }> = {
  REDLINE: { label: 'Redline the drawing', icon: 'edit-3' },
  RFI: { label: 'Raise an RFI', icon: 'help-circle' },
  FLAG: { label: 'Flag for review', icon: 'flag' },
  REVIEW: { label: 'Review the values', icon: 'eye' },
  ESCALATE: { label: 'Escalate', icon: 'arrow-up-circle' },
  BOM_CHANGE: { label: 'Change the BOM', icon: 'package' },
};
export const FAMILY: Record<string, string> = {
  CD_VS_FIELD: 'CD vs drone', RFDS_VS_CD: 'RFDS vs CD', DOCUMENT: 'Documents', EXTRACTION: 'Extraction', REVISION: 'Revisions',
  LOADING: 'Loading', MOUNT: 'Mount', STRUCTURAL: 'Structure', CABLE: 'Cable', REV0_BOM: 'REV 0 BOM',
};

export const sevOf = (x: R) => SEV[x.SEVERITY] ?? SEV.MEDIUM;
export const whereOf = (x: R) => (x.SECTOR ? `${SECTOR[x.SECTOR] ?? x.SECTOR}${x.POSITION ? ` · position ${x.POSITION}` : ''}` : 'Whole site');
export const fixOf = (x: R) => (x.TARGET_DOC ? `${x.TARGET_DOC}${x.TARGET_SHEET ? ` · sheet ${x.TARGET_SHEET}` : ''}` : '');
const value = (v: unknown) => {
  const t = show(v);
  if (t === '-') return 'Nothing recorded';
  const lines = t.split('\n');
  const text = lines.slice(0, 3).join('\n') + (lines.length > 3 ? `\n+ ${lines.length - 3} more` : '');
  return text.charAt(0).toUpperCase() + text.slice(1);
};

/** Two boxes: what was expected, what was found. Hidden when a finding has neither (e.g. a list of values to review). */
export function CompareStrip({ x, large }: { x: R; large?: boolean }) {
  const found = Array.isArray(x.FOUND?.v) && x.FOUND.v.length && typeof x.FOUND.v[0] === 'object' && 'field' in x.FOUND.v[0];
  if (found) return null;
  const box = (title: string, v: unknown, color: string) => (
    <View style={{ flex: 1, minWidth: 140, backgroundColor: color + '0F', borderRadius: 12, padding: space(large ? 3.5 : 2.5), borderWidth: 1, borderColor: color + '33' }}>
      <Text style={{ fontSize: 10, fontWeight: '800', letterSpacing: 0.8, color, textTransform: 'uppercase' }}>{title}</Text>
      <Text style={{ fontSize: large ? 16 : 13, fontWeight: '700', color: colors.text, marginTop: 3 }}>{value(v)}</Text>
    </View>
  );
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(2), alignItems: 'stretch' }}>
      {box('Expected', x.EXPECTED, colors.ok)}
      {box('Found', x.FOUND, sevOf(x).color)}
    </View>
  );
}

export function WhereChip({ x }: { x: R }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
      <Icon name="map-pin" size={13} color={colors.muted} />
      <Text style={{ fontSize: 12, fontWeight: '600', color: colors.muted }}>{whereOf(x)}</Text>
    </View>
  );
}

export function RuleCode({ code }: { code: string }) {
  return (
    <View style={{ backgroundColor: colors.surfaceAlt, borderRadius: 6, paddingHorizontal: 7, paddingVertical: 2, borderWidth: 1, borderColor: colors.border }}>
      <Text style={{ fontSize: 11, fontWeight: '700', color: colors.muted, fontFamily: 'monospace' as any }}>{code}</Text>
    </View>
  );
}

export function ActionPill({ x }: { x: R }) {
  const o = OUTCOME[x.OUTCOME] ?? { label: String(x.OUTCOME ?? ''), icon: 'chevron-right' as IconName };
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.soft, borderRadius: 999, paddingHorizontal: 11, paddingVertical: 5 }}>
      <Icon name={o.icon} size={13} color={colors.accent} />
      <Text style={{ fontSize: 12, fontWeight: '700', color: colors.accent }}>{o.label}</Text>
    </View>
  );
}

/** One finding in a list. */
export function FindingCard({ x }: { x: R }) {
  const sev = sevOf(x);
  const fix = fixOf(x);
  return (
    <Pressable onPress={() => router.push({ pathname: '/discrepancy/[id]', params: { id: x.DISC_ID } })} accessibilityRole="button"
      style={({ pressed }) => [{ flexDirection: 'row', backgroundColor: colors.card, borderRadius: 16, marginBottom: space(3), borderWidth: 1, borderColor: colors.border, overflow: 'hidden', opacity: pressed ? 0.85 : 1 }, shadow as any]}>
      <View style={{ width: 5, backgroundColor: sev.color }} />
      <View style={{ flex: 1, padding: space(4), gap: space(3) }}>
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: space(3) }}>
          <IconBadge name={sev.icon} color={sev.color} size={38} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text, lineHeight: 21 }}>{x.TITLE}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: space(2), marginTop: 5 }}>
              <WhereChip x={x} />
              <Text style={{ color: colors.border }}>•</Text>
              <Text style={{ fontSize: 12, color: colors.muted }}>{FAMILY[x.FAMILY] ?? x.FAMILY}</Text>
              <RuleCode code={x.RULE_ID} />
            </View>
          </View>
          <View style={{ alignItems: 'flex-end', gap: 6 }}>
            <Badge text={sev.label} color={sev.color} />
            <Badge text={x.STATUS} />
          </View>
        </View>
        <CompareStrip x={x} />
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
            <ActionPill x={x} />
            {fix ? <Text style={{ fontSize: 12, color: colors.muted }}>{`Fix in ${fix}`}</Text> : null}
          </View>
          <Icon name="chevron-right" size={18} color={colors.muted} />
        </View>
      </View>
    </Pressable>
  );
}

/** Small titled block used on the finding page. */
export function Panel({ icon, title, children }: { icon: IconName; title: string; children: React.ReactNode }) {
  return (
    <View style={[{ backgroundColor: colors.card, borderRadius: 16, padding: space(4), marginBottom: space(3), borderWidth: 1, borderColor: colors.border }, shadow as any]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), marginBottom: space(3) }}>
        <IconBadge name={icon} color={colors.accent} size={28} />
        <Text style={{ fontSize: 12, fontWeight: '800', letterSpacing: 1, color: colors.muted, textTransform: 'uppercase' }}>{title}</Text>
      </View>
      {children}
    </View>
  );
}
