// The Pipeline Run workspace views other than Stages: Overview, Documents, Activity and Findings.
// Each reads only existing endpoints, and only while its tab is open.
import { router } from 'expo-router';
import React from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { authedUrl } from '../../../lib/api';
import { when } from '../../../lib/format';
import { PipelineRun, PipelineStep, Row } from '../../../lib/types';
import { useApi } from '../../../lib/useApi';
import { colors, font, radius, space } from '../../theme';
import { Badge, Button, Card, Column, DataTable, EmptyState, ErrorView, IconName, Loading, Section } from '../../ui';
import { elapsed, REQUIRED_DOCS, RUN_STATE, runState, STATE, stageMeta, stageState } from './model';
import { StageIcon } from './StageFlow';

// ------------------------------------------------------------------ Overview
export function OverviewView({ steps, onOpenStage }: { steps: PipelineStep[]; onOpenStage: (key: string) => void }) {
  // same states and colours as the stage cards; selecting a stage opens it in the Stages view
  return (
    <Card>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: space(4), gap: space(3), flexWrap: 'wrap' }}>
        <View>
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }}>Execution flow</Text>
          <Text style={{ fontSize: 12.5, color: colors.muted, marginTop: 2 }}>Stages run in this order; each starts only after the one before succeeds.</Text>
        </View>
        <Button small kind="secondary" icon="git-branch" title="Open stage details" onPress={() => onOpenStage('')} />
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', rowGap: space(4) }}>
        {steps.map((st, i) => {
          const state = stageState(steps, i);
          const v = STATE[state];
          const meta = stageMeta(st.key, i);
          const done = state === 'COMPLETED' || state === 'REVIEW';
          return (
            <Pressable key={st.key} onPress={() => onOpenStage(st.key)} accessibilityRole="button" accessibilityLabel={`Stage ${i + 1}, ${meta.title}, ${v.label}`}
              style={({ hovered }: any) => ({ flexGrow: 1, flexBasis: 150, minWidth: 0, borderRadius: radius.md, padding: 4, backgroundColor: hovered ? colors.surfaceAlt : 'transparent' })}>
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <StageIcon state={state} icon={meta.icon} size={28} />
                {i < steps.length - 1 ? <View style={{ flex: 1, height: 2, marginHorizontal: 8, borderRadius: 1, backgroundColor: done ? STATE.COMPLETED.color : colors.border, opacity: done ? 0.55 : 1 }} /> : null}
              </View>
              <Text style={{ fontSize: 11, fontWeight: '600', color: colors.faint, letterSpacing: 0.3, marginTop: 8 }}>{`STAGE ${String(i + 1).padStart(2, '0')}`}</Text>
              <Text style={{ fontSize: 13, fontWeight: '600', color: state === 'PENDING' || state === 'BLOCKED' ? colors.muted : colors.text, marginTop: 2, paddingRight: 10 }} numberOfLines={2}>{meta.title}</Text>
              <Text style={{ fontSize: 12, fontWeight: '600', color: v.color, marginTop: 3 }}>{v.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </Card>
  );
}

// ------------------------------------------------------------------ Documents
export function DocumentsView({ run, steps }: { run: PipelineRun; steps: PipelineStep[] }) {
  const ingest = steps.find((s) => s.key === 'INGEST');
  const ran = !!ingest && (ingest.status === 'DONE' || ingest.status === 'FAILED');
  const d = useApi<any>(ran ? `/pipeline/runs/${run.RUN_ID}/steps/INGEST` : null);
  const docs: Row[] = d.data?.documents ?? [];
  const types = docs.reduce<Record<string, number>>((a, x) => ({ ...a, [x.DOC_TYPE]: (a[x.DOC_TYPE] ?? 0) + (x.STATUS === 'CURRENT' ? 1 : 0) }), {});
  const cols: Column<Row>[] = [
    { key: 'f', title: 'Document', flex: 2.4, render: (x) => <Text style={{ fontSize: 13, fontWeight: '500', color: colors.text }} numberOfLines={1}>{x.FILE_NAME}</Text> },
    { key: 't', title: 'Type', flex: 1.2, render: (x) => <Text style={{ fontSize: 12.5, color: colors.text }} numberOfLines={1}>{String(x.DOC_TYPE ?? '').replace(/_/g, ' ')}</Text> },
    { key: 'r', title: 'Revision', width: 90, render: (x) => <Text style={{ fontSize: 12.5, color: colors.text }}>{x.REVISION || '-'}</Text> },
    { key: 'fm', title: 'Format', width: 80, render: (x) => <Text style={{ fontSize: 12, color: colors.muted, fontFamily: font.mono }}>{x.FILE_FORMAT || '-'}</Text> },
    { key: 's', title: 'Status', width: 120, render: (x) => <Badge text={x.STATUS === 'CURRENT' ? 'Current' : x.STATUS === 'SUPERSEDED' ? 'Superseded' : x.STATUS} color={x.STATUS === 'CURRENT' ? colors.ok : colors.neutral} dot /> },
    { key: 'a', title: '', width: 110, align: 'right', render: (x) => <Button small kind="secondary" icon="download" title="Open" onPress={() => Linking.openURL(authedUrl(`/documents/${x.DOC_ID}/download`))} /> },
  ];
  if (!ran) return <Card><EmptyState icon="file-text" title="No documents for this run" text="Stage 1 did not run in this run, so no documents were registered." /></Card>;
  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading rows={5} />;
  return (
    <View>
      <Card>
        <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }}>Required documents</Text>
        <Text style={{ fontSize: 12.5, color: colors.muted, marginTop: 2, marginBottom: space(3) }}>Stage 1 stops the run when one of these is missing.</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(3) }}>
          {REQUIRED_DOCS.map((r) => {
            const ok = r.anyOf.some((t) => (types[t] ?? 0) > 0);
            const st = ok ? STATE.COMPLETED : STATE.FAILED;
            return (
              <View key={r.label} style={{ flexGrow: 1, flexBasis: 220, flexDirection: 'row', alignItems: 'center', gap: 10, padding: space(3), borderRadius: radius.md, borderWidth: 1, borderColor: st.line, backgroundColor: st.bg }}>
                <Text style={{ flex: 1, fontSize: 13, color: colors.text }}>{r.label}</Text>
                <Badge text={ok ? 'Available' : 'Missing'} color={st.color} dot />
              </View>
            );
          })}
        </View>
      </Card>
      <Section title={`Registered documents (${docs.length})`} subtitle={`${d.data.current_count ?? 0} current, ${d.data.superseded_count ?? 0} superseded. The pipeline always reads the current revision.`}>
        <DataTable columns={cols} rows={docs} keyFor={(x) => x.DOC_ID} minWidth={760} empty={<EmptyState icon="file-text" title="No documents registered" />} />
      </Section>
    </View>
  );
}

// ------------------------------------------------------------------ Activity
export function ActivityView({ run, steps, history, currentId, onSelectRun }: { run: PipelineRun; steps: PipelineStep[]; history: PipelineRun[]; currentId: string | null; onSelectRun: (id: string) => void }) {
  type Ev = { t: string; title: string; text?: string; state: ReturnType<typeof stageState> | 'INFO'; icon?: IconName };
  const ev: Ev[] = [{ t: run.STARTED_AT, title: 'Run started', text: `Triggered by ${run.TRIGGERED_BY ?? 'system'}`, state: 'INFO', icon: 'play' }];
  steps.forEach((s, i) => {
    const st = stageState(steps, i);
    const meta = stageMeta(s.key, i);
    if (s.started_at) ev.push({ t: s.started_at, title: `Stage ${i + 1} started: ${meta.title}`, state: 'INFO', icon: meta.icon });
    if (s.status === 'SKIPPED') ev.push({ t: s.finished_at ?? s.started_at ?? run.FINISHED_AT ?? run.STARTED_AT, title: `Stage ${i + 1} skipped: ${meta.title}`, text: s.message, state: st });
    else if (s.finished_at) ev.push({ t: s.finished_at, title: `Stage ${i + 1} ${s.status === 'FAILED' ? 'failed' : 'finished'}: ${meta.title}`, text: s.message, state: st });
  });
  for (const w of run.WARNINGS ?? []) ev.push({ t: run.FINISHED_AT ?? run.STARTED_AT, title: 'Warning', text: String(w), state: 'REVIEW' });
  if (run.FINISHED_AT) ev.push({ t: run.FINISHED_AT, title: `Run ${RUN_STATE[runState(run, steps)].label.toLowerCase()}`, text: elapsed(run.STARTED_AT, run.FINISHED_AT), state: 'INFO', icon: 'flag' });
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(4), alignItems: 'flex-start' }}>
      <Card style={{ flexGrow: 2, flexBasis: 460, marginBottom: 0 }}>
        <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text, marginBottom: space(4) }}>This run</Text>
        {ev.map((e, i) => {
          const tone = e.state === 'INFO' ? null : STATE[e.state];
          return (
            <View key={i} style={{ flexDirection: 'row', gap: space(3) }}>
              <View style={{ alignItems: 'center', width: 28 }}>
                {tone ? <StageIcon state={e.state as any} icon={e.icon ?? 'circle'} size={24} />
                  : <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }}><Text style={{ fontSize: 9, color: colors.muted }}>•</Text></View>}
                {i < ev.length - 1 ? <View style={{ width: 1.5, flex: 1, minHeight: 14, backgroundColor: colors.border, marginVertical: 3 }} /> : null}
              </View>
              <View style={{ flex: 1, paddingBottom: space(4) }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: space(3) }}>
                  <Text style={{ flex: 1, fontSize: 13, fontWeight: '600', color: tone ? tone.color : colors.text }}>{e.title}</Text>
                  <Text style={{ fontSize: 11.5, color: colors.faint, fontFamily: font.mono }}>{when(e.t).slice(11)}</Text>
                </View>
                {e.text ? <Text style={{ fontSize: 12.5, color: colors.muted, marginTop: 2, lineHeight: 18 }}>{e.text}</Text> : null}
              </View>
            </View>
          );
        })}
      </Card>
      <Card padded={false} style={{ flexGrow: 1, flexBasis: 320, marginBottom: 0, overflow: 'hidden' }}>
        <View style={{ paddingHorizontal: space(4), paddingVertical: space(3.5), borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }}>Run history</Text>
          <Text style={{ fontSize: 12.5, color: colors.muted, marginTop: 2 }}>Select a run to inspect it.</Text>
        </View>
        {history.map((h, i) => {
          const hs = RUN_STATE[runState(h, Array.isArray(h.STEPS) ? h.STEPS : null)];
          const sel = h.RUN_ID === currentId;
          return (
            <Pressable key={h.RUN_ID} onPress={() => onSelectRun(h.RUN_ID)} accessibilityRole="button" accessibilityState={{ selected: sel }}
              style={({ hovered }: any) => ({ paddingHorizontal: space(4), paddingVertical: space(3), borderBottomWidth: i === history.length - 1 ? 0 : 1, borderBottomColor: colors.border, backgroundColor: sel ? colors.soft : hovered ? colors.surfaceAlt : '#fff' })}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <Text style={{ fontSize: 12, fontFamily: font.mono, color: colors.text }} numberOfLines={1}>{h.RUN_ID}</Text>
                <Badge text={hs.label} color={hs.color} dot />
              </View>
              <Text style={{ fontSize: 12, color: colors.muted, marginTop: 3 }}>{`${when(h.STARTED_AT)}  ·  ${elapsed(h.STARTED_AT, h.FINISHED_AT) || '-'}`}</Text>
            </Pressable>
          );
        })}
      </Card>
    </View>
  );
}

// ------------------------------------------------------------------ Findings
export function FindingsView({ run, steps, siteId, onOpenTab }: { run: PipelineRun; steps: PipelineStep[]; siteId: string; onOpenTab?: (t: 'redlines' | 'discrepancies') => void }) {
  const rec = steps.find((s) => s.key === 'RECONCILE');
  const red = steps.find((s) => s.key === 'REDLINES');
  const d = useApi<any>(rec?.status === 'DONE' ? `/pipeline/runs/${run.RUN_ID}/steps/RECONCILE` : null);
  const r = useApi<any>(red?.status === 'DONE' ? `/pipeline/runs/${run.RUN_ID}/steps/REDLINES` : null);
  if (rec?.status !== 'DONE') return <Card><EmptyState icon="alert-circle" title="No findings for this run" text="Findings come from stage 3, which did not complete in this run." /></Card>;
  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading rows={4} />;
  const discs: Row[] = d.data.discrepancies ?? [];
  const reds: Row[] = r.data?.redlines ?? [];
  const rfis: Row[] = r.data?.rfis ?? [];
  const sev = (s: string) => (s === 'HIGH' || s === 'CRITICAL' ? colors.danger : s === 'MEDIUM' ? colors.warn : colors.info);
  return (
    <View>
      <Section title={`Discrepancies (${discs.length})`} subtitle="Mismatches between the construction drawing and the drone survey."
        right={onOpenTab && discs.length ? <Button small kind="secondary" title="All discrepancies" iconRight="arrow-right" onPress={() => onOpenTab('discrepancies')} /> : undefined} style={{ marginTop: 0 }}>
        <DataTable rows={discs} keyFor={(x) => x.DISC_ID} minWidth={760} onRowPress={(x) => router.push({ pathname: '/discrepancy/[id]', params: { id: x.DISC_ID } })}
          empty={<EmptyState icon="check-circle" title="No discrepancies" text="The drawing and the drone survey agree on every check." />}
          columns={[
            { key: 'rule', title: 'Rule', width: 90, render: (x) => <Text style={{ fontFamily: font.mono, fontSize: 12, color: colors.accent }}>{x.RULE_ID}</Text> },
            { key: 'title', title: 'Finding', flex: 3, render: (x) => <Text style={{ fontSize: 13, color: colors.text }} numberOfLines={2}>{x.TITLE}</Text> },
            { key: 'sev', title: 'Severity', width: 110, render: (x) => <Badge text={x.SEVERITY} color={sev(x.SEVERITY)} dot /> },
            { key: 'out', title: 'Outcome', width: 110, render: (x) => <Badge text={x.OUTCOME} color={colors.neutral} /> },
            { key: 'st', title: 'Status', width: 120, render: (x) => <Badge text={x.STATUS} /> },
          ]} />
      </Section>
      {red?.status === 'DONE' ? (
        <Section title={`Redlines (${reds.length}) and RFIs (${rfis.length})`} subtitle="Generated in stage 4 from the discrepancies above."
          right={onOpenTab && reds.length + rfis.length ? <Button small kind="secondary" title="Open Redlines & RFIs" iconRight="arrow-right" onPress={() => onOpenTab('redlines')} /> : undefined}>
          {!r.data ? <Loading rows={2} /> : (
            <DataTable<Row> rows={[...reds.map((x) => ({ ...x, _k: 'Redline' })), ...rfis.map((x) => ({ ...x, _k: 'RFI' }))]} keyFor={(x) => x.REDLINE_ID ?? x.RFI_ID} minWidth={720}
              empty={<EmptyState icon="check-circle" title="No redlines or RFIs" text="Nothing needed correcting in this run." />}
              columns={[
                { key: 'k', title: 'Type', width: 100, render: (x) => <Badge text={x._k} color={x._k === 'RFI' ? colors.info : colors.warn} /> },
                { key: 't', title: 'Subject', flex: 3, render: (x) => <Text style={{ fontSize: 13, color: colors.text }} numberOfLines={2}>{x.MARKUP ?? x.SUBJECT}</Text> },
                { key: 'w', title: 'Where', width: 150, render: (x) => <Text style={{ fontSize: 12.5, color: colors.muted }} numberOfLines={1}>{x._k === 'RFI' ? (x.TO_PARTY === 'AE_ENGINEER' ? 'To A&E Engineer' : 'To Admin') : `${x.DOC_TYPE} · sheet ${x.SHEET}`}</Text> },
                { key: 's', title: 'Status', width: 130, render: (x) => <Badge text={x.STATUS} dot /> },
              ]} />
          )}
        </Section>
      ) : null}
    </View>
  );
}
