// Pipeline Run: header with the run's facts and actions, an execution summary, the six stages as selectable workflow
// cards, the output of the selected stage, and a details inspector on the right (a drawer on narrow screens).
// Stages run strictly in order on the backend; this screen only shows what the run reports and never bypasses gating.
import { router, useLocalSearchParams } from 'expo-router';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Modal, Pressable, ScrollView, Text, View, useWindowDimensions } from 'react-native';
import { api, ApiError } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { when } from '../../lib/format';
import { PipelineRun, PipelineStep } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, font, radius, shadowPopover, space } from '../theme';
import { Badge, Banner, Button, Card, ConfirmDialog, Dialog, EmptyState, ErrorView, Icon, Loading, Section, SegmentedTabs, Skeleton, TabItem } from '../ui';
import { Inspector, SiteTab } from './pipeline/Inspector';
import { elapsed, RUN_STATE, runState, STATE, stageState } from './pipeline/model';
import { StageFlow } from './pipeline/StageFlow';
import { ActivityView, DocumentsView, FindingsView, OverviewView } from './pipeline/Views';
import { StepDetailView } from './PipelineSteps';
import { ExtractionStage } from './extraction/Extraction';
import { RunNotes, RunResult } from './RunResult';

function Fact({ k, v, mono }: { k: string; v?: string | null; mono?: boolean }) {
  return (
    <View style={{ minWidth: 110 }}>
      <Text style={{ fontSize: 11.5, color: colors.muted }}>{k}</Text>
      <Text style={{ fontSize: 13, color: colors.text, fontWeight: '500', marginTop: 2, fontFamily: mono ? font.mono : undefined }} numberOfLines={1} selectable>{v || '-'}</Text>
    </View>
  );
}

function Metric({ label, value, color, hint }: { label: string; value: string | number; color?: string; hint?: string }) {
  return (
    <View style={{ flexGrow: 1, flexBasis: 128, backgroundColor: '#fff', borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, paddingHorizontal: space(3.5), paddingVertical: space(3) }}>
      <Text style={{ fontSize: 12, color: colors.muted }} numberOfLines={1}>{label}</Text>
      <Text style={{ fontSize: 20, fontWeight: '600', color: color ?? colors.text, marginTop: 4, letterSpacing: -0.3 }}>{value}</Text>
      {hint ? <Text style={{ fontSize: 11.5, color: colors.faint, marginTop: 2 }} numberOfLines={1}>{hint}</Text> : null}
    </View>
  );
}

type View_ = 'overview' | 'stages' | 'documents' | 'activity' | 'findings';
const VIEWS: View_[] = ['overview', 'stages', 'documents', 'activity', 'findings'];

/** Stage shown when nothing is selected: the running one, else the failed one, else the stage that caused a stop, else the last that ran. */
function defaultStage(steps: PipelineStep[]): string {
  const skipped = steps.findIndex((s) => s.status === 'SKIPPED');
  return (steps.find((s) => s.status === 'RUNNING') ?? steps.find((s) => s.status === 'FAILED') ?? (skipped > 0 ? steps[skipped - 1] : undefined)
    ?? [...steps].reverse().find((s) => s.status === 'DONE') ?? steps[0]).key;
}

export function Pipeline({ siteId, siteName, onFinished, onOpenTab }: { siteId: string; siteName?: string; onFinished?: () => void; onOpenTab?: (t: SiteTab) => void }) {
  const { can } = useAuth();
  const { width } = useWindowDimensions();
  const latest = useApi<PipelineRun | null>(`/pipeline/sites/${siteId}/latest`);
  const history = useApi<PipelineRun[]>(`/pipeline/runs?site_id=${siteId}&limit=10`);
  const [started, setStarted] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [confirm, setConfirm] = useState<'run' | 'cancel' | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const params = useLocalSearchParams<{ view?: string }>();
  const [view, setViewState] = useState<View_>(VIEWS.includes(params.view as View_) ? (params.view as View_) : 'overview');
  const setView = (v: View_) => { setViewState(v); router.setParams({ view: v }); };

  const activeLatestId = started ?? latest.data?.RUN_ID ?? null;
  const id = selectedRunId ?? activeLatestId;
  const isViewingHistorical = selectedRunId !== null && selectedRunId !== activeLatestId;

  // the run is re-read every 500 ms while it is running, so the stages update live
  const run = useApi<PipelineRun>(id ? `/pipeline/runs/${id}` : null, { pollMs: 500, keepPolling: (r) => r.STATUS === 'RUNNING' });
  const r = run.data;
  const steps: PipelineStep[] | null = r && Array.isArray(r.STEPS) ? r.STEPS : null;
  const stageKey = steps ? (selectedStage && steps.some((s) => s.key === selectedStage) ? selectedStage : defaultStage(steps)) : null;
  const stageIdx = steps && stageKey ? steps.findIndex((s) => s.key === stageKey) : -1;
  const stage = steps && stageIdx >= 0 ? steps[stageIdx] : null;

  // one request for the selected stage's detail, shared by the inspector and the stage output; re-read when its status changes
  const wantDetail = !!(r && stage && (stage.status === 'DONE' || stage.status === 'FAILED' || stage.status === 'SKIPPED'));
  const detail = useApi<any>(wantDetail ? `/pipeline/runs/${r!.RUN_ID}/steps/${stage!.key}?s=${stage!.status}` : null);

  // tell the site screen when a run finishes so the other tabs show the new results
  const was = useRef<string | undefined>(undefined);
  useEffect(() => {
    const now = r?.STATUS;
    if (was.current === 'RUNNING' && now && now !== 'RUNNING') {
      onFinished?.();
      void history.reload();
      void latest.reload();
    }
    was.current = now;
  }, [r?.STATUS, onFinished, history, latest]);

  const counts = useMemo(() => {
    const c = { COMPLETED: 0, RUNNING: 0, REVIEW: 0, FAILED: 0, SKIPPED: 0, PENDING: 0, BLOCKED: 0 };
    steps?.forEach((_, i) => { c[stageState(steps, i)] += 1; });
    return c;
  }, [steps]);

  const start = async () => {
    setConfirm(null); setErr(null); setSelectedRunId(null); setSelectedStage(null);
    try {
      const res = await api.post<{ run_id: string }>(`/pipeline/sites/${siteId}/start`);
      setStarted(res.run_id);
      void run.reload();
      void history.reload();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  const cancel = async () => {
    setConfirm(null); setErr(null);
    try {
      await api.post(`/pipeline/sites/${siteId}/cancel`);
      setStarted(null);
      void run.reload(); void latest.reload(); void history.reload();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  const refresh = () => { void latest.reload(); void history.reload(); void run.reload(); if (wantDetail) void detail.reload(); };

  if (latest.error) return <ErrorView error={latest.error} onRetry={latest.reload} />;
  if (latest.loading && !id) return <Loading rows={4} />;

  const canRun = can('SCOPER', 'REVIEWER');
  const running = r?.STATUS === 'RUNNING';
  const rs = runState(r, steps);
  const rsv = RUN_STATE[rs];
  const failed = steps?.find((s) => s.status === 'FAILED');
  const failedIdx = steps ? steps.findIndex((s) => s.status === 'FAILED') : -1;
  const runningStep = steps?.find((s) => s.status === 'RUNNING');
  const wide = width >= 1280;
  const selectStage = (k: string) => { setSelectedStage(k); if (!wide) setDrawer(true); };
  const findingCount = Number(steps?.find((s) => s.key === 'RECONCILE')?.counts?.rules ?? 0);
  const viewTabs: TabItem<View_>[] = [
    { key: 'overview', label: 'Overview', icon: 'layout' }, { key: 'stages', label: 'Stages', icon: 'git-branch' },
    { key: 'documents', label: 'Documents', icon: 'file-text' }, { key: 'activity', label: 'Activity', icon: 'activity' },
    { key: 'findings', label: 'Findings', icon: 'alert-circle', count: findingCount > 0 ? findingCount : undefined },
  ];

  const inspector = r && steps && stage ? (
    <Inspector run={r} steps={steps} stepKey={stage.key} index={stageIdx} state={stageState(steps, stageIdx)} detail={detail.data} detailLoading={wantDetail && !detail.data && !detail.error}
      onOpenTab={onOpenTab} onClose={!wide ? () => setDrawer(false) : undefined} onCollapse={wide ? () => setInspectorOpen(false) : undefined} />
  ) : null;

  return (
    <View>
      {/* header */}
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: space(4), flexWrap: 'wrap', marginBottom: space(4) }}>
        <View style={{ flexShrink: 1, minWidth: 280 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2.5), flexWrap: 'wrap' }}>
            <Text style={{ fontSize: 20, fontWeight: '600', color: colors.text, letterSpacing: -0.3 }}>Pipeline run</Text>
            <Badge text={rsv.label} color={rsv.color} dot />
            {running && runningStep ? <Text style={{ fontSize: 12.5, color: STATE.RUNNING.color }}>{`Now: ${runningStep.label}`}</Text> : null}
          </View>
          <View style={{ flexDirection: 'row', gap: space(5), marginTop: space(3), flexWrap: 'wrap' }}>
            <Fact k="Site ID" v={siteId} />
            {siteName ? <Fact k="Site name" v={siteName} /> : null}
            <Fact k="Run ID" v={r?.RUN_ID} mono />
            <Fact k="Started" v={r ? when(r.STARTED_AT) : null} />
            <Fact k={running ? 'Elapsed' : 'Duration'} v={r ? elapsed(r.STARTED_AT, r.FINISHED_AT) : null} />
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: space(2), alignItems: 'center', flexWrap: 'wrap', maxWidth: '100%', flexShrink: 1 }}>
          <Button kind="secondary" icon="rotate-cw" title="Refresh" onPress={refresh} />
          {history.data?.length ? <Button kind="secondary" icon="clock" title="Run history" onPress={() => setHistoryOpen(true)} /> : null}
          {canRun && running ? <Button kind="secondary" icon="square" title="Cancel run" onPress={() => setConfirm('cancel')} /> : null}
          {canRun ? <Button icon={running ? 'loader' : 'play'} title={running ? 'Running...' : 'Run pipeline'} disabled={running} onPress={() => (r ? setConfirm('run') : void start())} /> : null}
        </View>
      </View>

      {id ? <SegmentedTabs tabs={viewTabs} value={view} onChange={setView} style={{ marginBottom: space(4) }} /> : null}

      {!canRun && (view === 'overview' || view === 'stages') ? <Banner kind="neutral" icon="lock">Only a Scoper or a Reviewer can run the pipeline. You can review every stage below.</Banner> : null}
      {isViewingHistorical ? (
        <Banner kind="info" title={`Viewing an earlier run: ${id}`} action={<Button small kind="secondary" title="Back to latest run" onPress={() => { setSelectedRunId(null); setSelectedStage(null); }} />}>
          Its stages and results are shown below.
        </Banner>
      ) : null}
      {err ? <ErrorView error={err} /> : null}
      {run.error ? <ErrorView error={run.error} onRetry={run.reload} /> : null}

      {!id ? (
        <Card>
          <EmptyState icon="git-commit" title="This site has not been run yet"
            text="The pipeline checks the documents, compares the drawing with the drone survey, and then builds the bill of materials."
            action={canRun ? <Button icon="play" title="Run pipeline" onPress={start} /> : undefined} />
        </Card>
      ) : !r ? (
        <View style={{ gap: space(3) }}>
          <View style={{ flexDirection: 'row', gap: space(3) }}>{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} width={`${100 / 6 - 2}%`} height={64} r={10} />)}</View>
          <Loading rows={6} />
        </View>
      ) : (
        <>
          {view === 'overview' ? (
            <>
          {/* execution summary */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(2.5), marginBottom: space(4) }}>
            <Metric label="Total stages" value={steps?.length ?? 6} />
            <Metric label="Completed" value={counts.COMPLETED + counts.REVIEW} color={counts.COMPLETED + counts.REVIEW ? STATE.COMPLETED.color : undefined} />
            <Metric label="Running" value={counts.RUNNING} color={counts.RUNNING ? STATE.RUNNING.color : undefined} />
            <Metric label="Review required" value={counts.REVIEW} color={counts.REVIEW ? STATE.REVIEW.color : undefined} hint="Finished with findings" />
            <Metric label="Failed or skipped" value={counts.FAILED + counts.SKIPPED + counts.BLOCKED} color={counts.FAILED ? STATE.FAILED.color : counts.SKIPPED ? '#64748B' : undefined}
              hint={counts.FAILED ? `${counts.FAILED} failed, ${counts.SKIPPED + counts.BLOCKED} not run` : counts.SKIPPED ? `${counts.SKIPPED} skipped` : undefined} />
            <Metric label={running ? 'Elapsed' : 'Duration'} value={elapsed(r.STARTED_AT, r.FINISHED_AT) || '-'} />
          </View>

          {/* gating and failure messages */}
          {rs === 'STOPPED' ? (
            <Banner kind="warn" title="Pipeline stopped after stage 4."
              action={onOpenTab ? <Button small kind="secondary" icon="edit-3" title="Open Redlines & RFIs" onPress={() => onOpenTab('redlines')} /> : undefined}>
              Resolve all open redlines and RFIs before proceeding with RFDS extraction and BOM generation.
            </Banner>
          ) : null}
          {rs === 'FAILED' ? (
            <Banner kind="danger" title={failed ? `Failed at stage ${failedIdx + 1}: ${failed.label}` : 'The run failed'}
              action={canRun ? <Button small kind="secondary" icon="rotate-cw" title="Retry" onPress={() => setConfirm('run')} /> : undefined}>
              <Text style={{ fontSize: 13, color: colors.text, lineHeight: 19 }}>{failed?.message || (r.WARNINGS && r.WARNINGS[0]) || 'An unexpected error occurred.'}</Text>
            </Banner>
          ) : null}

              {steps ? <OverviewView steps={steps} onOpenStage={(k) => { if (k) setSelectedStage(k); setView('stages'); }} /> : null}
              {!running && rs !== 'FAILED' ? <View style={{ marginTop: space(2) }}><RunNotes run={r} /><RunResult run={r} siteId={siteId} /></View> : null}
            </>
          ) : null}
          {view === 'stages' ? (
            <>
          {/* gating and failure messages */}
          {rs === 'STOPPED' ? (
            <Banner kind="warn" title="Pipeline stopped after stage 4."
              action={onOpenTab ? <Button small kind="secondary" icon="edit-3" title="Open Redlines & RFIs" onPress={() => onOpenTab('redlines')} /> : undefined}>
              Resolve all open redlines and RFIs before proceeding with RFDS extraction and BOM generation.
            </Banner>
          ) : null}
          {rs === 'FAILED' ? (
            <Banner kind="danger" title={failed ? `Failed at stage ${failedIdx + 1}: ${failed.label}` : 'The run failed'}
              action={canRun ? <Button small kind="secondary" icon="rotate-cw" title="Retry" onPress={() => setConfirm('run')} /> : undefined}>
              <Text style={{ fontSize: 13, color: colors.text, lineHeight: 19 }}>{failed?.message || (r.WARNINGS && r.WARNINGS[0]) || 'An unexpected error occurred.'}</Text>
            </Banner>
          ) : null}

          {!steps ? (
            <Card><EmptyState icon="clock" title="No stage tracking for this run" text="This run was recorded before stage tracking. Run the pipeline again to see its stages." /></Card>
          ) : (
            <View style={{ flexDirection: 'row', gap: space(5), alignItems: 'flex-start' }}>
              <View style={{ flex: 1, minWidth: 0 }}>
                {wide && !inspectorOpen ? (
                  <View style={{ flexDirection: 'row', justifyContent: 'flex-end', marginBottom: space(3) }}>
                    <Button small kind="secondary" icon="sidebar" title="Show stage details" onPress={() => setInspectorOpen(true)} />
                  </View>
                ) : null}
                <StageFlow steps={steps} selected={stageKey!} onSelect={selectStage} />

                {stage && (stage.status === 'DONE' || stage.status === 'FAILED' || (stage.key === 'DESIGN' && stage.status === 'SKIPPED')) ? (
                  <Section title={`Stage output: ${stage.label}`} subtitle="What this stage read, compared or produced.">
                    <Card>
                      {detail.error ? <ErrorView error={detail.error} onRetry={detail.reload} /> : !detail.data ? <Loading rows={3} />
                        : stage.key === 'EXTRACT' || stage.key === 'DESIGN' ? <ExtractionStage run={r} step={stage} x={detail.data} siteId={siteId} wide={Math.min(width, 1880) - (width >= 900 ? 236 : 0) - 96 - (wide && inspectorOpen ? 388 : 0) >= 940} />
                        : <StepDetailView x={detail.data} runId={r.RUN_ID} siteId={siteId} stepKey={stage.key} stepStatus={stage.status} reload={() => { void detail.reload(); void run.reload(); }} />}
                    </Card>
                  </Section>
                ) : null}

              </View>

              {wide && inspector && inspectorOpen ? (
                <View style={{ width: 368, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, overflow: 'hidden', backgroundColor: '#fff', position: 'sticky' as any, top: 0 }}>
                  {inspector}
                </View>
              ) : null}
            </View>
          )}
            </>
          ) : null}
          {view === 'documents' && steps ? <DocumentsView run={r} steps={steps} /> : null}
          {view === 'activity' && steps ? <ActivityView run={r} steps={steps} history={history.data ?? []} currentId={id}
            onSelectRun={(rid) => { setSelectedRunId(rid === activeLatestId ? null : rid); setSelectedStage(null); }} /> : null}
          {view === 'findings' && steps ? <FindingsView run={r} steps={steps} siteId={siteId} onOpenTab={onOpenTab} /> : null}
          {view !== 'overview' && view !== 'stages' && !steps ? <Card><EmptyState icon="clock" title="No stage tracking for this run" text="Run the pipeline again to see this view." /></Card> : null}
        </>
      )}

      {/* narrow screens: the inspector opens as a drawer */}
      {!wide && inspector && view === 'stages' ? (
        <Modal visible={drawer} transparent animationType="none" onRequestClose={() => setDrawer(false)}>
          <View style={{ flex: 1, flexDirection: 'row' }}>
            <Pressable style={{ flex: 1, backgroundColor: 'rgba(15,23,42,0.45)' }} onPress={() => setDrawer(false)} accessibilityLabel="Close details" />
            <View style={[{ width: Math.min(400, width), backgroundColor: '#fff' }, shadowPopover as any]}>
              <ScrollView>{inspector}</ScrollView>
            </View>
          </View>
        </Modal>
      ) : null}

      <Dialog open={historyOpen} onClose={() => setHistoryOpen(false)} title="Run history" width={640}>
        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, overflow: 'hidden' }}>
          {(history.data ?? []).map((h, i, a) => {
            const hSteps = Array.isArray(h.STEPS) ? h.STEPS : [];
            const hs = RUN_STATE[runState(h, hSteps.length ? hSteps : null)];
            const sel = h.RUN_ID === id;
            return (
              <Pressable key={h.RUN_ID} onPress={() => { setSelectedRunId(h.RUN_ID === activeLatestId ? null : h.RUN_ID); setSelectedStage(null); setHistoryOpen(false); }}
                style={({ hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: space(3), padding: space(3), borderBottomWidth: i === a.length - 1 ? 0 : 1, borderBottomColor: colors.border, backgroundColor: sel ? colors.soft : hovered ? colors.surfaceAlt : '#fff' })}>
                <Icon name={sel ? 'eye' : 'clock'} size={14} color={sel ? colors.accent : colors.faint} />
                <View style={{ flex: 1, minWidth: 0 }}>
                  <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                    <Text style={{ fontFamily: font.mono, fontSize: 12, color: colors.text }} numberOfLines={1}>{h.RUN_ID}</Text>
                    {h.RUN_ID === activeLatestId ? <Badge text="Latest" color={colors.info} /> : null}
                  </View>
                  <Text style={{ fontSize: 12, color: colors.muted, marginTop: 2 }}>{`${when(h.STARTED_AT)}  ·  ${hSteps.filter((x) => x.status === 'DONE').length} of ${hSteps.length || '-'} stages  ·  ${elapsed(h.STARTED_AT, h.FINISHED_AT) || '-'}`}</Text>
                </View>
                <Badge text={hs.label} color={hs.color} dot />
              </Pressable>
            );
          })}
        </View>
      </Dialog>

      <ConfirmDialog open={confirm === 'run'} title="Run the pipeline again?" confirmText="Run pipeline"
        message="Every stage runs again from the site's current documents, in order, and this run's results are rebuilt. A stage runs only if the one before it succeeds."
        onConfirm={start} onCancel={() => setConfirm(null)} />
      <ConfirmDialog open={confirm === 'cancel'} danger title="Cancel this run?" confirmText="Cancel run"
        message="The stage in progress stops and the run is marked as cancelled. You can run the pipeline again afterwards."
        onConfirm={cancel} onCancel={() => setConfirm(null)} />
    </View>
  );
}
