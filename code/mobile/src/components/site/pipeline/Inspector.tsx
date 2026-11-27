// Right-hand details inspector for the selected stage: header, execution information, inputs, outputs, log,
// errors and warnings, and the actions this user can take from here. Content comes from the run and the stage detail.
import { Feather } from '@expo/vector-icons';
import React, { useState } from 'react';
import { ActivityIndicator, Linking, Pressable, Text, View } from 'react-native';
import { authedUrl } from '../../../lib/api';
import { when } from '../../../lib/format';
import { PipelineRun, PipelineStep } from '../../../lib/types';
import { colors, font, radius, space, tint } from '../../theme';
import { Badge, Button, IconName } from '../../ui';
import { duration } from '../StageTimeline';
import { inspect, IoItem, REQUIRED_DOCS, stageMeta, StageState, stageWarnings, STATE } from './model';
import { StageIcon, StateBadge } from './StageFlow';

export type SiteTab = 'overview' | 'redlines' | 'bom' | 'discrepancies';

function Block({ title, count, children, initiallyOpen = true }: { title: string; count?: number; children: React.ReactNode; initiallyOpen?: boolean }) {
  const [open, setOpen] = useState(initiallyOpen);
  return (
    <View style={{ borderTopWidth: 1, borderTopColor: colors.border }}>
      <Pressable onPress={() => setOpen((o) => !o)} accessibilityRole="button" accessibilityState={{ expanded: open }}
        style={({ hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: space(4), paddingVertical: space(3), backgroundColor: hovered ? colors.surfaceAlt : 'transparent' })}>
        <Text style={{ flex: 1, fontSize: 11.5, fontWeight: '600', color: colors.muted, letterSpacing: 0.5, textTransform: 'uppercase' }}>{title}</Text>
        {count != null ? <Text style={{ fontSize: 11, fontWeight: '600', color: colors.muted, backgroundColor: colors.surfaceAlt, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>{count}</Text> : null}
        <Feather name={open ? 'chevron-up' : 'chevron-down'} size={14} color={colors.faint} />
      </Pressable>
      {open ? <View style={{ paddingHorizontal: space(4), paddingBottom: space(4), gap: space(2) }}>{children}</View> : null}
    </View>
  );
}

function Meta({ k, v, mono }: { k: string; v?: string | null; mono?: boolean }) {
  return (
    <View style={{ flexDirection: 'row', gap: space(3) }}>
      <Text style={{ width: 96, fontSize: 12.5, color: colors.muted }}>{k}</Text>
      <Text style={{ flex: 1, fontSize: 12.5, color: colors.text, fontFamily: mono ? font.mono : undefined }} selectable numberOfLines={2}>{v || '-'}</Text>
    </View>
  );
}

function Io({ it }: { it: IoItem }) {
  const body = (hovered = false) => (
    <View style={{ flexDirection: 'row', gap: 10, alignItems: 'flex-start', padding: space(2.5), borderRadius: radius.md, borderWidth: 1, borderColor: hovered ? colors.borderStrong : colors.border, backgroundColor: '#fff' }}>
      {it.icon ? <Feather name={it.icon as IconName} size={14} color={it.href ? colors.accent : colors.muted} style={{ marginTop: 2 }} /> : null}
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={{ fontSize: 12.5, fontWeight: '500', color: it.href ? colors.accent : colors.text }} numberOfLines={2}>{it.label}</Text>
        {it.detail ? <Text style={{ fontSize: 11.5, color: colors.muted, marginTop: 1 }} numberOfLines={2}>{it.detail}</Text> : null}
      </View>
      {it.status ? <Badge text={it.status} color={it.statusColor ?? colors.neutral} /> : null}
    </View>
  );
  if (!it.href) return body();
  return <Pressable onPress={() => Linking.openURL(authedUrl(it.href!))} accessibilityRole="link">{({ hovered }: any) => body(hovered)}</Pressable>;
}

export function Inspector({ run, steps, stepKey, state, index, detail, detailLoading, onOpenTab, onClose, onCollapse }: {
  run: PipelineRun; steps: PipelineStep[]; stepKey: string; state: StageState; index: number; detail: any; detailLoading: boolean;
  onOpenTab?: (t: SiteTab) => void; onClose?: () => void; onCollapse?: () => void;
}) {
  const st = steps[index];
  const meta = stageMeta(stepKey, index);
  const io = inspect(stepKey, detail, st);
  io.notes = io.notes.filter((x) => x && x !== st.message);
  const warnings = stageWarnings(run, stepKey);
  const failedAt = steps.findIndex((x) => x.status === 'FAILED');
  const registered = st.key === 'INGEST' && st.status === 'DONE' ? st.counts ?? {} : null;

  const log: { t: string; text: string; tone?: 'danger' | 'warn' }[] = [];
  if (st.started_at) log.push({ t: when(st.started_at).slice(11), text: 'Stage started' });
  if (st.message && st.status !== 'SKIPPED' && st.status !== 'FAILED') log.push({ t: st.finished_at ? when(st.finished_at).slice(11) : '', text: st.message });
  if (st.status === 'FAILED') log.push({ t: st.finished_at ? when(st.finished_at).slice(11) : '', text: 'Error raised (see above)', tone: 'danger' });
  for (const w of warnings) log.push({ t: '', text: w, tone: 'warn' });
  if (st.finished_at && st.status !== 'SKIPPED') log.push({ t: when(st.finished_at).slice(11), text: st.status === 'FAILED' ? 'Stage failed' : 'Stage finished' });

  const actions: { label: string; icon: IconName; go: () => void }[] = [];
  if (onOpenTab) {
    if (stepKey === 'INGEST' || stepKey === 'EXTRACT' || stepKey === 'DESIGN') actions.push({ label: 'View documents', icon: 'file-text', go: () => onOpenTab('overview') });
    if (stepKey === 'RECONCILE') actions.push({ label: 'View discrepancies', icon: 'alert-triangle', go: () => onOpenTab('discrepancies') });
    if (stepKey === 'REDLINES' || state === 'SKIPPED') actions.push({ label: 'View redlines & RFIs', icon: 'edit-3', go: () => onOpenTab('redlines') });
    if (stepKey === 'BOM' && st.status === 'DONE') actions.push({ label: 'View BOM', icon: 'list', go: () => onOpenTab('bom') });
  }
  const drawing = stepKey === 'REDLINES' ? detail?.files?.redlined_cd_pdf : null;

  return (
    <View style={{ backgroundColor: '#fff' }}>
      {/* A. header */}
      <View style={{ padding: space(4), gap: space(3) }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3) }}>
          <StageIcon state={state} icon={meta.icon} size={34} />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={{ fontSize: 11, fontWeight: '600', color: colors.faint, letterSpacing: 0.4 }}>{`STAGE ${String(index + 1).padStart(2, '0')} OF ${steps.length}`}</Text>
            <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }} numberOfLines={2}>{meta.title}</Text>
          </View>
          {onCollapse ? (
            <Pressable onPress={onCollapse} accessibilityRole="button" accessibilityLabel="Hide stage details"
              style={({ hovered }: any) => ({ width: 30, height: 30, borderRadius: 8, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border, backgroundColor: hovered ? colors.surfaceAlt : '#fff' })}>
              <Feather name="chevrons-right" size={16} color={colors.muted} />
            </Pressable>
          ) : null}
          {onClose ? <Pressable onPress={onClose} accessibilityLabel="Close details" style={{ padding: 6 }}><Feather name="x" size={18} color={colors.muted} /></Pressable> : null}
        </View>
        <StateBadge state={state} />
        <Text style={{ fontSize: 13, color: colors.muted, lineHeight: 19 }}>{meta.description}</Text>
      </View>

      {/* F. errors / why it did not run (shown first when present) */}
      {state === 'FAILED' ? (
        <View style={{ marginHorizontal: space(4), marginBottom: space(4), padding: space(3), borderRadius: radius.md, backgroundColor: tint.danger.bg, borderWidth: 1, borderColor: tint.danger.line, gap: 6 }}>
          <Text style={{ fontSize: 12.5, fontWeight: '600', color: tint.danger.fg }}>Error</Text>
          <Text style={{ fontSize: 12.5, color: colors.text, fontFamily: font.mono, lineHeight: 18 }} selectable>{st.message || 'The stage failed without a message.'}</Text>
          <Text style={{ fontSize: 12, color: colors.muted }}>{`Component: ${meta.title}. Later stages did not run. Fix the cause above, then run the pipeline again.`}</Text>
        </View>
      ) : state === 'SKIPPED' ? (
        <View style={{ marginHorizontal: space(4), marginBottom: space(4), padding: space(3), borderRadius: radius.md, backgroundColor: tint.warn.bg, borderWidth: 1, borderColor: tint.warn.line, gap: 6 }}>
          <Text style={{ fontSize: 12.5, fontWeight: '600', color: tint.warn.fg }}>Why this stage was skipped</Text>
          <Text style={{ fontSize: 12.5, color: colors.text, lineHeight: 18 }}>{st.message || 'Open redlines or RFIs from stages 3 and 4 have to be resolved first.'}</Text>
        </View>
      ) : state === 'BLOCKED' ? (
        <View style={{ marginHorizontal: space(4), marginBottom: space(4), padding: space(3), borderRadius: radius.md, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ fontSize: 12.5, color: colors.text }}>{`Not run because stage ${failedAt + 1} failed. Stages run only after the one before succeeds.`}</Text>
        </View>
      ) : null}

      {/* B. execution information */}
      <Block title="Execution">
        <Meta k="Started" v={st.started_at ? when(st.started_at) : null} />
        <Meta k="Completed" v={st.finished_at && st.status !== 'SKIPPED' ? when(st.finished_at) : state === 'RUNNING' ? 'In progress' : null} />
        <Meta k="Duration" v={duration(st.duration_ms) || null} />
        <Meta k="Run ID" v={run.RUN_ID} mono />
        <Meta k="Last updated" v={when(run.FINISHED_AT ?? st.finished_at ?? st.started_at ?? run.STARTED_AT)} />
      </Block>

      {/* stage 1: required documents availability, from what the stage registered */}
      {registered ? (
        <Block title="Required documents">
          {REQUIRED_DOCS.map((r) => {
            const ok = r.anyOf.some((t) => Number(registered[t] ?? 0) > 0);
            return (
              <View key={r.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Feather name={ok ? 'check-circle' : 'x-circle'} size={14} color={ok ? STATE.COMPLETED.color : STATE.FAILED.color} />
                <Text style={{ fontSize: 12.5, color: colors.text, flex: 1 }}>{r.label}</Text>
                <Text style={{ fontSize: 12, color: ok ? colors.muted : STATE.FAILED.color }}>{ok ? 'Available' : 'Missing'}</Text>
              </View>
            );
          })}
        </Block>
      ) : null}

      {/* C/D. inputs and outputs */}
      {detailLoading ? (
        <View style={{ padding: space(4), borderTopWidth: 1, borderTopColor: colors.border, flexDirection: 'row', gap: 8, alignItems: 'center' }}>
          <ActivityIndicator size="small" color={colors.accent} /><Text style={{ fontSize: 12.5, color: colors.muted }}>Loading stage details</Text>
        </View>
      ) : st.status === 'DONE' || st.status === 'FAILED' ? (
        <>
          <Block title="Inputs" count={io.inputs.length} initiallyOpen={io.inputs.length <= 8}>
            {io.inputs.length ? io.inputs.map((it, k) => <Io key={k} it={it} />) : <Text style={{ fontSize: 12.5, color: colors.muted }}>No inputs recorded for this stage.</Text>}
          </Block>
          <Block title="Outputs" count={io.outputs.length}>
            {io.outputs.length ? io.outputs.map((it, k) => <Io key={k} it={it} />) : <Text style={{ fontSize: 12.5, color: colors.muted }}>No outputs recorded for this stage.</Text>}
          </Block>
        </>
      ) : null}

      {/* E. log */}
      <Block title="Execution log" count={log.length + io.notes.length} initiallyOpen={state !== 'PENDING'}>
        {log.length + io.notes.length === 0 ? <Text style={{ fontSize: 12.5, color: colors.muted }}>Nothing logged yet.</Text> : null}
        {log.map((l, k) => (
          <View key={`l${k}`} style={{ flexDirection: 'row', gap: 10 }}>
            <Text style={{ width: 54, fontSize: 11.5, color: colors.faint, fontFamily: font.mono }}>{l.t}</Text>
            <Text style={{ flex: 1, fontSize: 12.5, lineHeight: 18, color: l.tone === 'danger' ? STATE.FAILED.color : l.tone === 'warn' ? '#B45309' : colors.text }}>{l.text}</Text>
          </View>
        ))}
        {io.notes.map((n, k) => (
          <View key={`n${k}`} style={{ flexDirection: 'row', gap: 10 }}>
            <Text style={{ width: 54, fontSize: 11.5, color: colors.faint }}>note</Text>
            <Text style={{ flex: 1, fontSize: 12.5, lineHeight: 18, color: colors.text }}>{n}</Text>
          </View>
        ))}
      </Block>

      {/* G. actions */}
      {actions.length || drawing ? (
        <View style={{ borderTopWidth: 1, borderTopColor: colors.border, padding: space(4), gap: space(2) }}>
          {drawing ? <Button kind="secondary" icon="file-text" title="View redlined drawing" onPress={() => Linking.openURL(authedUrl(`/files/${drawing}`))} /> : null}
          {actions.map((a) => <Button key={a.label} kind="secondary" icon={a.icon} title={a.label} onPress={a.go} />)}
        </View>
      ) : null}
    </View>
  );
}
