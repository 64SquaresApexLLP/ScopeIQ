// The six pipeline stages as a connected timeline. Stages run strictly in order: after a failed stage the rest are
// shown as blocked, and stages 5-6 show as skipped while redlines or RFIs from stages 3-4 are open.
import { Feather } from '@expo/vector-icons';
import React from 'react';
import { ActivityIndicator, Text, View, useWindowDimensions } from 'react-native';
import { when } from '../../lib/format';
import { PipelineStep } from '../../lib/types';
import { colors, tint } from '../theme';

export const STAGE_INFO: Record<string, string> = {
  INGEST: 'Register the site documents and pick the latest revision of each.',
  EXTRACT: 'Read the construction drawings and the drone survey.',
  RECONCILE: 'Compare the drawings with the drone survey.',
  REDLINES: 'Turn each mismatch into a redline or an RFI.',
  DESIGN: 'Read equipment changes from the RFDS and the MA/SA report.',
  BOM: 'Build the bill of materials from the BOM rules and catalog.',
};

export const duration = (ms: number | null | undefined) =>
  ms == null ? '' : ms < 950 ? `${ms} ms` : ms < 60000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.floor(ms / 60000)} min ${Math.round((ms % 60000) / 1000)} s`;

export type StageView = 'DONE' | 'RUNNING' | 'FAILED' | 'SKIPPED' | 'BLOCKED' | 'PENDING';

/** What a step should look like, taking the stages before it into account. */
export function stageView(steps: PipelineStep[], i: number): StageView {
  const st = steps[i];
  const failedAt = steps.findIndex((x) => x.status === 'FAILED');
  if (st.status === 'DONE' || st.status === 'RUNNING' || st.status === 'FAILED' || st.status === 'SKIPPED') return st.status;
  if (failedAt >= 0 && i > failedAt) return 'BLOCKED';
  return 'PENDING';
}

export const VIEW: Record<StageView, { text: string; color: string; bg: string; icon: React.ComponentProps<typeof Feather>['name'] | null }> = {
  DONE: { text: 'Completed', color: tint.ok.fg, bg: tint.ok.bg, icon: 'check' },
  RUNNING: { text: 'Running', color: tint.info.fg, bg: tint.info.bg, icon: null },
  FAILED: { text: 'Failed', color: tint.danger.fg, bg: tint.danger.bg, icon: 'x' },
  SKIPPED: { text: 'Skipped', color: '#64748B', bg: '#F1F5F9', icon: 'minus' },
  BLOCKED: { text: 'Not run', color: '#94A3B8', bg: '#F8FAFC', icon: 'lock' },
  PENDING: { text: 'Pending', color: '#94A3B8', bg: '#F8FAFC', icon: null },
};

export function StageNode({ view, n, size = 30 }: { view: StageView; n: number; size?: number }) {
  const v = VIEW[view];
  const ring = view === 'RUNNING' ? colors.info : view === 'DONE' ? colors.ok : view === 'FAILED' ? colors.danger : colors.border;
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: view === 'DONE' ? colors.ok : view === 'FAILED' ? colors.danger : v.bg,
      borderWidth: view === 'DONE' || view === 'FAILED' ? 0 : 1.5, borderColor: ring, alignItems: 'center', justifyContent: 'center' }}>
      {view === 'RUNNING' ? <ActivityIndicator size="small" color={colors.info} />
        : v.icon ? <Feather name={v.icon} size={size * 0.46} color={view === 'DONE' || view === 'FAILED' ? '#fff' : v.color} />
        : <Text style={{ fontSize: 12, fontWeight: '600', color: v.color }}>{n}</Text>}
    </View>
  );
}

function detailLine(st: PipelineStep, view: StageView, steps: PipelineStep[]): string {
  if (view === 'RUNNING') return st.started_at ? `Started ${when(st.started_at).slice(11)}` : 'In progress';
  if (view === 'DONE' || view === 'FAILED') return [st.finished_at ? when(st.finished_at).slice(11) : '', duration(st.duration_ms)].filter(Boolean).join('  ·  ');
  if (view === 'SKIPPED') return 'Resolve open redlines and RFIs first';
  if (view === 'BLOCKED') return `Blocked by stage ${steps.findIndex((x) => x.status === 'FAILED') + 1}`;
  return 'Waiting';
}

export function StageTimeline({ steps }: { steps: PipelineStep[] }) {
  const { width } = useWindowDimensions();
  const horizontal = width >= 1100;
  if (horizontal) {
    return (
      <View style={{ flexDirection: 'row' }}>
        {steps.map((st, i) => {
          const view = stageView(steps, i);
          const v = VIEW[view];
          const nextDone = i < steps.length - 1 && view === 'DONE';
          return (
            <View key={st.key} style={{ flex: 1, minWidth: 0 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <StageNode view={view} n={i + 1} />
                {i < steps.length - 1 ? <View style={{ flex: 1, height: 2, marginHorizontal: 8, borderRadius: 1, backgroundColor: nextDone ? colors.ok : colors.border }} /> : null}
              </View>
              <View style={{ paddingRight: 14, marginTop: 10 }}>
                <Text style={{ fontSize: 11, fontWeight: '600', color: colors.faint, letterSpacing: 0.3 }}>STAGE {i + 1}</Text>
                <Text style={{ fontSize: 13.5, fontWeight: '600', color: view === 'BLOCKED' || view === 'PENDING' ? colors.muted : colors.text, marginTop: 2 }} numberOfLines={2}>{st.label}</Text>
                <Text style={{ fontSize: 12, fontWeight: '600', color: v.color, marginTop: 4 }}>{v.text}</Text>
                <Text style={{ fontSize: 11.5, color: colors.muted, marginTop: 2 }} numberOfLines={2}>{detailLine(st, view, steps)}</Text>
              </View>
            </View>
          );
        })}
      </View>
    );
  }
  return (
    <View>
      {steps.map((st, i) => {
        const view = stageView(steps, i);
        const v = VIEW[view];
        return (
          <View key={st.key} style={{ flexDirection: 'row', gap: 12 }}>
            <View style={{ alignItems: 'center' }}>
              <StageNode view={view} n={i + 1} size={26} />
              {i < steps.length - 1 ? <View style={{ width: 2, flex: 1, minHeight: 18, marginVertical: 4, backgroundColor: view === 'DONE' ? colors.ok : colors.border }} /> : null}
            </View>
            <View style={{ flex: 1, paddingBottom: 14 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                <Text style={{ fontSize: 13.5, fontWeight: '600', color: view === 'BLOCKED' || view === 'PENDING' ? colors.muted : colors.text, flex: 1 }}>{`${i + 1}. ${st.label}`}</Text>
                <Text style={{ fontSize: 12, fontWeight: '600', color: v.color }}>{v.text}</Text>
              </View>
              <Text style={{ fontSize: 12, color: colors.muted, marginTop: 2 }}>{detailLine(st, view, steps)}</Text>
            </View>
          </View>
        );
      })}
    </View>
  );
}
