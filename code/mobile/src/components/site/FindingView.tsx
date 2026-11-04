// How a finding (discrepancy) looks: severity accent, a plain title, where it is, what was expected vs found,
// and what to do about it. Shared by the Discrepancies tab, the stage 3 list and the finding page.
import { router } from 'expo-router';
import React, { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { SECTOR, show, when } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { colors, shadow, space } from '../theme';
import { Badge, Button, Icon, IconBadge, IconName } from '../ui';

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
  const found = Array.isArray(x.FOUND?.v) && x.FOUND.v.length > 0 && typeof x.FOUND.v[0] === 'object' && x.FOUND.v[0] !== null && 'field' in x.FOUND.v[0];
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

export const eventLabel = (h: R, revLabel: string) => {
  const act = h.ACTION;
  const user = h.ACTOR_USER_ID || 'User';
  if (act === 'SEND_TO_AE') return `Sent to A&E by ${user}`;
  if (act === 'ACKNOWLEDGE') return `Acknowledged by A&E (${user})`;
  if (act === 'COMPLETE' || act === 'INCORPORATE' || act === 'AE_SUBMIT_REVISION')
    return `Drawing updated (${revLabel}) by A&E (${user})`;
  if (act === 'REMOVE_REDLINE') return `Redline removed & closed by ${user}`;
  if (act === 'CREATE_REDLINE') return `Redline markup drafted by ${user}`;
  if (act === 'CONFIRM') return `Confirmed by ${user}`;
  if (act === 'DISMISS') return `Dismissed by ${user}`;
  return `${h.FROM_STATE ? `${h.FROM_STATE} ➔ ` : ''}${h.TO_STATE || act} by ${user}`;
};

/** One finding in a list. */
export function FindingCard({ x, onReload }: { x: R; onReload?: () => void }) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const sev = sevOf(x);
  const fix = fixOf(x);

  const isRedlineRemoved = x.AE_STATUS === 'REDLINE_REMOVED' || x.STATUS === 'CLOSED' || (x.STATUS === 'RESOLVED' && !x.REDLINE_PENDING_REMOVAL);
  const isAeRevised = !isRedlineRemoved && (x.AE_STATUS === 'IMPROVED_REV_RECEIVED' || x.REASON_CODE === 'RC-AE-REVISED' || x.REDLINE_PENDING_REMOVAL);
  const isSentToAe = !isRedlineRemoved && !isAeRevised && (x.AE_STATUS === 'SENT_TO_AE' || x.STATUS === 'REDLINED');
  const revLabel = x.AE_REVISION_LABEL || 'REV 2';

  const handleSendToAe = async (e: any) => {
    e?.stopPropagation?.();
    if (busy) return;
    setBusy(true);
    try {
      await api.post(`/discrepancies/${x.DISC_ID}/send-to-ae`, {});
      onReload?.();
    } catch (err) {
      console.error(err);
    } finally {
      setBusy(false);
    }
  };

  const handleAeSubmitRevision = async (e: any) => {
    e?.stopPropagation?.();
    if (busy) return;
    setBusy(true);
    try {
      await api.post(`/discrepancies/${x.DISC_ID}/submit-ae-revision`, {
        revision: 'REV 2',
        comment: 'Improved CD revision incorporating redline and drone measurements',
      });
      onReload?.();
    } catch (err) {
      console.error(err);
    } finally {
      setBusy(false);
    }
  };

  const handleRemoveRedline = async (e: any) => {
    e?.stopPropagation?.();
    if (busy) return;
    setBusy(true);
    try {
      await api.post(`/discrepancies/${x.DISC_ID}/remove-redline`, {});
      onReload?.();
    } catch (err) {
      console.error(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Pressable
      onPress={() => router.push({ pathname: '/discrepancy/[id]', params: { id: x.DISC_ID } })}
      accessibilityRole="button"
      style={({ pressed }) => [
        {
          flexDirection: 'row',
          backgroundColor: colors.card,
          borderRadius: 16,
          marginBottom: space(3),
          borderWidth: 1,
          borderColor: isRedlineRemoved ? '#86efac' : isAeRevised ? '#10b981' : isSentToAe ? '#3b82f6' : colors.border,
          overflow: 'hidden',
          opacity: pressed ? 0.85 : 1,
        },
        shadow as any,
      ]}
    >
      <View style={{ width: 6, backgroundColor: isRedlineRemoved ? '#10b981' : isAeRevised ? '#10b981' : sev.color }} />
      <View style={{ flex: 1, padding: space(4), gap: space(3) }}>
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: space(3) }}>
          <IconBadge name={isRedlineRemoved ? 'check' : isAeRevised ? 'check-circle' : sev.icon} color={isRedlineRemoved ? '#10b981' : isAeRevised ? '#10b981' : sev.color} size={38} />
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
            {isRedlineRemoved ? (
              <Badge text="RESOLVED" color={colors.ok} />
            ) : (
              <Badge text={sev.label} color={sev.color} />
            )}
            {isRedlineRemoved ? (
              <Badge text={`${revLabel} UPDATED`} color={colors.ok} />
            ) : isAeRevised ? (
              <Badge text={`${revLabel} RECEIVED`} color={colors.ok} />
            ) : isSentToAe ? (
              <Badge text="SENT TO A&E" color={colors.primary} />
            ) : (
              <Badge text={x.STATUS} />
            )}
          </View>
        </View>

        <CompareStrip x={x} />

        {/* When redline has been updated and removed (Old / Resolved discrepancy) */}
        {isRedlineRemoved ? (
          <View
            style={{
              backgroundColor: '#f0fdf4',
              borderColor: '#86efac',
              borderWidth: 1,
              borderRadius: 12,
              padding: space(3),
              gap: 6,
            }}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Icon name="check-circle" size={15} color="#16a34a" />
              <Text style={{ fontSize: 13, fontWeight: '800', color: '#15803d' }}>
                Resolved in {revLabel} • Redline updated & removed
              </Text>
            </View>
            <Text style={{ fontSize: 12, color: '#166534', lineHeight: 18 }}>
              A&E updated CD drawing ({revLabel}) matching measured values ({show(x.FOUND)}). The redline markup has been incorporated and cleared.
            </Text>
          </View>
        ) : null}

        {/* When A&E improved version received: display banner until redline removed */}
        {isAeRevised ? (
          <View
            style={{
              backgroundColor: '#ecfdf5',
              borderColor: '#10b981',
              borderWidth: 1,
              borderRadius: 12,
              padding: space(3),
              gap: 8,
            }}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1, minWidth: 200 }}>
                <Icon name="check-circle" size={16} color="#059669" />
                <Text style={{ fontSize: 13, fontWeight: '800', color: '#065f46' }}>
                  Improved version ({revLabel}) received from A&E
                </Text>
              </View>
              {['SCOPER', 'REVIEWER', 'ADMIN'].includes(user?.role ?? '') ? (
                <Pressable
                  onPress={handleRemoveRedline}
                  disabled={busy}
                  style={{
                    backgroundColor: '#059669',
                    paddingHorizontal: 12,
                    paddingVertical: 6,
                    borderRadius: 8,
                  }}
                >
                  <Text style={{ color: '#fff', fontSize: 12, fontWeight: '700' }}>
                    {busy ? 'Removing...' : 'Remove redline'}
                  </Text>
                </Pressable>
              ) : null}
            </View>
            <Text style={{ fontSize: 12, color: '#047857', lineHeight: 18 }}>
              A&E updated CD drawing ({revLabel}) with measured values. This discrepancy remains visible in the list until the redline is removed.
            </Text>
          </View>
        ) : null}

        {/* When in review by A&E */}
        {isSentToAe && !isAeRevised ? (
          <View
            style={{
              backgroundColor: '#eff6ff',
              borderColor: '#93c5fd',
              borderWidth: 1,
              borderRadius: 10,
              paddingHorizontal: space(3),
              paddingVertical: space(2),
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 8,
            }}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Icon name="send" size={13} color="#2563eb" />
              <Text style={{ fontSize: 12.5, fontWeight: '700', color: '#1d4ed8' }}>
                Sent to A&E • In review for revised drawing
              </Text>
            </View>
            {['AE_ENGINEER', 'ADMIN'].includes(user?.role ?? '') ? (
              <Pressable
                onPress={handleAeSubmitRevision}
                disabled={busy}
                style={{
                  backgroundColor: '#2563eb',
                  paddingHorizontal: 10,
                  paddingVertical: 5,
                  borderRadius: 6,
                }}
              >
                <Text style={{ color: '#fff', fontSize: 11.5, fontWeight: '700' }}>
                  {busy ? 'Submitting...' : 'Send improved REV 2'}
                </Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}

        {/* Discrepancy History & Revisions progression */}
        {((Array.isArray(x.HISTORY) && x.HISTORY.length > 0) || isAeRevised || isRedlineRemoved || isSentToAe) ? (
          <View
            style={{
              backgroundColor: colors.surfaceAlt,
              borderRadius: 12,
              padding: space(3),
              gap: 8,
              borderWidth: 1,
              borderColor: colors.border,
            }}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Icon name="clock" size={13} color={colors.muted} />
                <Text style={{ fontSize: 11, fontWeight: '800', letterSpacing: 0.6, color: colors.muted, textTransform: 'uppercase' }}>
                  Discrepancy History & Revisions
                </Text>
              </View>
              {isRedlineRemoved ? (
                <Badge text="RESOLVED (REDLINE REMOVED)" color={colors.ok} />
              ) : isAeRevised ? (
                <Badge text={`${revLabel} MATCHED`} color={colors.ok} />
              ) : isSentToAe ? (
                <Badge text="SENT TO A&E" color={colors.primary} />
              ) : null}
            </View>

            {/* Progression: CD REV 1 -> Drone measured -> CD REV 2 */}
            <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 8, backgroundColor: colors.card, padding: space(2), borderRadius: 8, borderWidth: 1, borderColor: colors.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <Text style={{ fontSize: 11, color: colors.muted }}>CD REV 1:</Text>
                <Text style={{ fontSize: 12, fontWeight: '700', color: colors.danger }}>{show(x.EXPECTED)}</Text>
              </View>
              <Text style={{ color: colors.muted, fontSize: 11 }}>➔</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <Text style={{ fontSize: 11, color: colors.muted }}>Drone measured:</Text>
                <Text style={{ fontSize: 12, fontWeight: '700', color: colors.text }}>{show(x.FOUND)}</Text>
              </View>
              {isAeRevised || isRedlineRemoved ? (
                <>
                  <Text style={{ color: colors.muted, fontSize: 11 }}>➔</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <Text style={{ fontSize: 11, color: colors.muted }}>CD {revLabel}:</Text>
                    <Text style={{ fontSize: 12, fontWeight: '700', color: '#15803d' }}>{show(x.FOUND)} (Corrected)</Text>
                  </View>
                </>
              ) : null}
            </View>

            {/* Event Timeline list */}
            {Array.isArray(x.HISTORY) && x.HISTORY.length > 0 ? (
              <View style={{ gap: 5, marginTop: 2, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 6 }}>
                {x.HISTORY.map((h: R, idx: number) => (
                  <View key={h.EVENT_ID || idx} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: idx === x.HISTORY.length - 1 ? '#10b981' : colors.muted }} />
                    <Text style={{ fontSize: 11, color: colors.muted, minWidth: 95 }}>{when(h.EVENT_TS)}</Text>
                    <Text style={{ fontSize: 11.5, fontWeight: idx === x.HISTORY.length - 1 ? '700' : '500', color: colors.text, flex: 1 }}>
                      {eventLabel(h, revLabel)}
                    </Text>
                  </View>
                ))}
              </View>
            ) : null}
          </View>
        ) : null}

        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
          {isRedlineRemoved ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#ecfdf5', borderRadius: 999, paddingHorizontal: 11, paddingVertical: 5 }}>
              <Icon name="check" size={13} color="#059669" />
              <Text style={{ fontSize: 12, fontWeight: '700', color: '#059669' }}>Historical Discrepancy (Closed)</Text>
            </View>
          ) : (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
              <ActionPill x={x} />
              {fix ? <Text style={{ fontSize: 12, color: colors.muted }}>{`Fix in ${fix}`}</Text> : null}
              {!isSentToAe && !isAeRevised && ['SCOPER', 'REVIEWER', 'ADMIN'].includes(user?.role ?? '') && x.STATUS !== 'CLOSED' ? (
                <Pressable
                  onPress={handleSendToAe}
                  disabled={busy}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 5,
                    backgroundColor: colors.surfaceAlt,
                    borderWidth: 1,
                    borderColor: colors.accent,
                    borderRadius: 999,
                    paddingHorizontal: 10,
                    paddingVertical: 4,
                  }}
                >
                  <Icon name="send" size={12} color={colors.accent} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: colors.accent }}>
                    {busy ? 'Sending...' : 'Send to A&E'}
                  </Text>
                </Pressable>
              ) : null}
            </View>
          )}
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
