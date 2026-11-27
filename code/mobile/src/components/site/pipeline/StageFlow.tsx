// The six stages as connected, selectable workflow cards (vertical flow; two columns of cards are avoided so the
// execution order stays obvious). The selected card is outlined in blue and drives the inspector.
import { Feather } from '@expo/vector-icons';
import React from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { when } from '../../../lib/format';
import { PipelineStep } from '../../../lib/types';
import { colors, radius, shadowLift, space } from '../../theme';
import { duration } from '../StageTimeline';
import { STATE, StageState, stageMeta, stageState, stageSummary } from './model';

export function StateBadge({ state }: { state: StageState }) {
  const v = STATE[state];
  return (
    <View accessibilityLabel={`Status: ${v.label}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 8, height: 22, borderRadius: 6, backgroundColor: v.bg, borderWidth: 1, borderColor: v.line, alignSelf: 'flex-start' }}>
      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: v.color }} />
      <Text style={{ fontSize: 11.5, fontWeight: '600', color: v.color }}>{v.label}</Text>
    </View>
  );
}

export function StageIcon({ state, icon, size = 36 }: { state: StageState; icon: any; size?: number }) {
  const v = STATE[state];
  const solid = state === 'COMPLETED' || state === 'FAILED' || state === 'REVIEW';
  return (
    <View style={{ width: size, height: size, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: solid ? v.color : v.bg, borderWidth: solid ? 0 : 1, borderColor: v.line }}>
      {state === 'RUNNING' ? <ActivityIndicator size="small" color={v.color} />
        : <Feather name={state === 'COMPLETED' ? 'check' : state === 'FAILED' ? 'x' : state === 'REVIEW' ? 'alert-triangle' : state === 'PENDING' ? icon : v.icon} size={size * 0.45} color={solid ? '#fff' : v.color} />}
    </View>
  );
}

function timing(st: PipelineStep, state: StageState): string {
  if (state === 'RUNNING') return st.started_at ? `Started ${when(st.started_at).slice(11)}` : 'Starting';
  const parts = [st.finished_at ? `Finished ${when(st.finished_at).slice(11)}` : '', duration(st.duration_ms)].filter(Boolean);
  return parts.join('  ·  ');
}

export function StageFlow({ steps, selected, onSelect }: { steps: PipelineStep[]; selected: string; onSelect: (key: string) => void }) {
  return (
    <View accessibilityRole="list">
      {steps.map((st, i) => {
        const state = stageState(steps, i);
        const meta = stageMeta(st.key, i);
        const v = STATE[state];
        const on = st.key === selected;
        const dim = state === 'PENDING' || state === 'BLOCKED' || state === 'SKIPPED';
        const next = i < steps.length - 1 ? stageState(steps, i + 1) : null;
        const lineDone = state === 'COMPLETED' || state === 'REVIEW';
        return (
          <View key={st.key}>
            <Pressable onPress={() => onSelect(st.key)} accessibilityRole="button" accessibilityState={{ selected: on }}
              accessibilityLabel={`Stage ${i + 1}, ${meta.title}, ${v.label}`}
              style={({ hovered }: any) => [{
                flexDirection: 'row', gap: space(3.5), alignItems: 'flex-start', padding: space(4), borderRadius: radius.lg, borderWidth: 1,
                backgroundColor: on ? '#F5F8FF' : '#fff', borderColor: on ? colors.accent : hovered ? colors.borderStrong : colors.border,
              }, on ? ({ boxShadow: '0 0 0 3px rgba(37,99,235,0.12)' } as any) : hovered ? shadowLift : null]}>
              {/* status accent on the left edge */}
              <View style={{ position: 'absolute', left: -1, top: 12, bottom: 12, width: 3, borderRadius: 2, backgroundColor: dim ? 'transparent' : v.color }} />
              <StageIcon state={state} icon={meta.icon} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
                  <Text style={{ fontSize: 11, fontWeight: '600', color: colors.faint, letterSpacing: 0.4 }}>{`STAGE ${String(i + 1).padStart(2, '0')}`}</Text>
                  <Text style={{ fontSize: 14.5, fontWeight: '600', color: dim ? colors.muted : colors.text }}>{meta.title}</Text>
                </View>
                <Text style={{ fontSize: 12.5, color: colors.muted, marginTop: 2 }} numberOfLines={1}>{meta.description}</Text>
                <Text style={{ fontSize: 12.5, color: state === 'FAILED' ? STATE.FAILED.color : dim ? colors.faint : colors.text, marginTop: 6, lineHeight: 18 }} numberOfLines={2}>
                  {state === 'BLOCKED' ? `Not run: stage ${steps.findIndex((x) => x.status === 'FAILED') + 1} failed.` : state === 'PENDING' ? 'Waiting for the previous stage.' : stageSummary(st)}
                </Text>
              </View>
              <View style={{ alignItems: 'flex-end', gap: 6, minWidth: 120 }}>
                <StateBadge state={state} />
                <Text style={{ fontSize: 11.5, color: colors.faint }}>{timing(st, state)}</Text>
              </View>
            </Pressable>
            {next ? (
              <View style={{ height: 18, marginLeft: space(4) + 17, width: 2, backgroundColor: lineDone ? STATE.COMPLETED.color : colors.border, opacity: lineDone ? 0.55 : 1 }} />
            ) : null}
          </View>
        );
      })}
    </View>
  );
}
