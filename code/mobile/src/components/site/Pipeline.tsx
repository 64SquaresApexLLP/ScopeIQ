// Pipeline tab: what the backend does for this site, step by step, live while it runs. Each finished step opens to
// the rows it produced; the last section turns the approved redlines into the next drawing revision.
import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { api, ApiError } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { when } from '../../lib/format';
import { PipelineRun } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, space } from '../theme';
import { Badge, Button, Card, Empty, ErrorView, KV, Loading, Muted, Row, Title } from '../ui';
import { ImplementChanges } from './ImplementChanges';
import { PipelineSteps } from './PipelineSteps';

export function Pipeline({ siteId, onFinished }: { siteId: string; onFinished?: () => void }) {
  const { can } = useAuth();
  const latest = useApi<PipelineRun | null>(`/pipeline/sites/${siteId}/latest`);
  const history = useApi<PipelineRun[]>(`/pipeline/runs?site_id=${siteId}&limit=10`);
  const [started, setStarted] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState<boolean>(true);
  const [err, setErr] = useState<ApiError | null>(null);
  const [version, setVersion] = useState(0);               // bumped when a redline changes, so the approved count refreshes

  // Allow switching between selected historical run and the latest/current active run
  const activeLatestId = started ?? latest.data?.RUN_ID ?? null;
  const id = selectedRunId ?? activeLatestId;
  const isViewingHistorical = selectedRunId !== null && selectedRunId !== activeLatestId;

  // Poll every 500ms while running so stage-by-stage progress is animated live
  const run = useApi<PipelineRun>(id ? `/pipeline/runs/${id}` : null, { pollMs: 500, keepPolling: (r) => r.STATUS === 'RUNNING' });

  // tell the site screen when a run finishes so the other tabs show the new results
  const was = useRef<string | undefined>(undefined);
  useEffect(() => {
    const now = run.data?.STATUS;
    if (was.current === 'RUNNING' && now && now !== 'RUNNING') {
      onFinished?.();
      void history.reload();
      void latest.reload();
    }
    was.current = now;
  }, [run.data?.STATUS, onFinished, history, latest]);

  const start = async () => {
    setErr(null);
    setSelectedRunId(null);
    try {
      const r = await api.post<{ run_id: string }>(`/pipeline/sites/${siteId}/start`);
      setStarted(r.run_id);
      void run.reload();
      void history.reload();
    } catch (e) {
      setErr(e as ApiError);
    }
  };

  if (latest.error) return <ErrorView error={latest.error} onRetry={latest.reload} />;
  if (latest.loading && !id) return <Loading />;
  const r = run.data;
  const steps = r && Array.isArray(r.STEPS) ? r.STEPS : null;
  const running = r?.STATUS === 'RUNNING';
  const canRun = can('SCOPER', 'REVIEWER');

  // Stage progress analysis
  const failedStep = steps?.find((s) => s.status === 'FAILED');
  const isFailed = r?.STATUS === 'FAILED' || !!failedStep;
  const runningStep = steps?.find((s) => s.status === 'RUNNING');
  const runningIndex = steps ? steps.findIndex((s) => s.status === 'RUNNING') : -1;
  const completedCount = steps?.filter((s) => s.status === 'DONE').length ?? 0;
  const totalSteps = steps?.length ?? 9;
  const progressPct = totalSteps > 0 ? Math.round((completedCount / totalSteps) * 100) : 0;

  return (
    <View>
      {/* Prominent Action Card: Run Pipeline */}
      <Card style={{ marginBottom: space(3), borderColor: running ? colors.info : isFailed ? colors.danger : colors.primary, borderWidth: 1.5, backgroundColor: colors.surface }}>
        <Row style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: space(1) }}>
          <Title style={{ fontSize: 18 }}>Automated Scoping Pipeline</Title>
          <Badge
            text={running ? 'RUNNING' : isFailed ? 'FAILED' : r?.STATUS ?? 'READY'}
            color={running ? colors.info : isFailed ? colors.danger : r?.STATUS === 'SUCCEEDED' ? colors.ok : colors.primary}
          />
        </Row>
        <Muted style={{ marginBottom: space(2) }}>
          Executes multi-stage automated scoping: (1) Ingests registered site documents with latest revision check, (2) Extracts Drone point cloud / video and CD CAD / drawing data in parallel, (3) Reconciles discrepancies, and (4) Generates BOM & redlines.
        </Muted>

        {canRun ? (
          <Row style={{ alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
            <Button
              kind="primary"
              title={running ? 'Running Pipeline...' : isFailed ? '▶ Re-run Pipeline (Retry)' : r ? '▶ Run Pipeline (Re-run)' : '▶ Run Pipeline'}
              disabled={running}
              onPress={start}
            />
            {r?.RUN_ID ? <Muted style={{ fontSize: 12 }}>{`Run ID: ${r.RUN_ID} (${when(r.STARTED_AT)})`}</Muted> : null}
          </Row>
        ) : (
          <Muted style={{ color: colors.warn }}>Scoper or Reviewer role required to execute the pipeline.</Muted>
        )}
      </Card>

      {/* Historical Run Inspection Alert if an older run is active */}
      {isViewingHistorical ? (
        <Card style={{ marginBottom: space(2), backgroundColor: '#EFF6FF', borderColor: colors.info, borderWidth: 1 }}>
          <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
            <View style={{ flex: 1, marginRight: space(2) }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: colors.info }}>
                {`Viewing Historical Run: ${id}`}
              </Text>
              <Muted style={{ fontSize: 12 }}>You are inspecting a past run stored in SQLite. You can review its stages and extracted comparison records below.</Muted>
            </View>
            <Button small kind="secondary" title="Return to Latest Run" onPress={() => setSelectedRunId(null)} />
          </Row>
        </Card>
      ) : null}

      {/* Run History: Stored in SQLite CORE.PIPELINE_RUN */}
      {history.data && history.data.length > 0 ? (
        <Card style={{ marginBottom: space(3), backgroundColor: colors.surface }}>
          <Pressable onPress={() => setShowHistory(!showHistory)} accessibilityRole="button">
            <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <Row style={{ alignItems: 'center', gap: space(1) }}>
                <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>📜 Pipeline Run History</Text>
                <Badge text={`${history.data.length} Stored Runs (SQLite)`} color={colors.primary} />
              </Row>
              <Text style={{ color: colors.primary, fontSize: 13, fontWeight: '700' }}>{showHistory ? 'Hide ▲' : 'Show ▼'}</Text>
            </Row>
          </Pressable>

          {showHistory ? (
            <View style={{ marginTop: space(2) }}>
              <Muted style={{ fontSize: 12, marginBottom: space(1.5) }}>
                Every execution progress and final result is persisted in the local SQLite database (<Text style={{ fontFamily: 'monospace' }}>CORE.PIPELINE_RUN</Text>). Tap any run to inspect its stages.
              </Muted>
              {history.data.map((h) => {
                const isSelected = h.RUN_ID === id;
                const hSteps = Array.isArray(h.STEPS) ? h.STEPS : [];
                const hDone = hSteps.filter((s: any) => s.status === 'DONE').length;
                const hTotal = hSteps.length || 9;
                const hStatus = h.STATUS ?? 'UNKNOWN';

                return (
                  <Pressable
                    key={h.RUN_ID}
                    onPress={() => setSelectedRunId(h.RUN_ID)}
                    style={{
                      padding: space(1.5),
                      marginBottom: space(1),
                      borderRadius: 8,
                      borderWidth: 1.5,
                      borderColor: isSelected ? colors.primary : colors.border,
                      backgroundColor: isSelected ? '#F0F7FF' : colors.surfaceAlt,
                    }}
                  >
                    <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                      <View style={{ flex: 1 }}>
                        <Row style={{ alignItems: 'center', gap: space(1), marginBottom: 2 }}>
                          <Text style={{ fontSize: 13, fontWeight: '700', color: isSelected ? colors.primary : colors.text, fontFamily: 'monospace' }}>
                            {h.RUN_ID}
                          </Text>
                          {isSelected ? <Badge text="ACTIVE VIEW" color={colors.primary} /> : null}
                          {h.RUN_ID === activeLatestId ? <Badge text="LATEST" color={colors.ok} /> : null}
                        </Row>
                        <Muted style={{ fontSize: 12 }}>
                          {`Started ${when(h.STARTED_AT)}${h.FINISHED_AT ? ` • Finished ${when(h.FINISHED_AT)}` : ''} • By ${h.TRIGGERED_BY ?? 'system'}`}
                        </Muted>
                      </View>
                      <Row style={{ alignItems: 'center', gap: space(1) }}>
                        <Badge
                          text={`${hDone}/${hTotal} Stages`}
                          color={(hStatus as string) === 'DONE' || hStatus === 'SUCCEEDED' ? colors.ok : hStatus === 'RUNNING' ? colors.info : colors.danger}
                        />
                        <Badge
                          text={hStatus}
                          color={(hStatus as string) === 'DONE' || hStatus === 'SUCCEEDED' ? colors.ok : hStatus === 'RUNNING' ? colors.info : colors.danger}
                        />
                      </Row>
                    </Row>
                  </Pressable>
                );
              })}
            </View>
          ) : null}
        </Card>
      ) : null}

      {/* Failure Alert Box: Stops execution and raises alert with error message */}
      {isFailed ? (
        <Card style={{ backgroundColor: '#FEF2F2', borderColor: colors.danger, borderWidth: 2, marginBottom: space(3), padding: space(3) }}>
          <Row style={{ alignItems: 'flex-start', gap: space(2) }}>
            <Text style={{ fontSize: 24, lineHeight: 28 }}>🚨</Text>
            <View style={{ flex: 1 }}>
              <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ fontSize: 16, fontWeight: '800', color: colors.danger }}>
                  {failedStep ? `Pipeline Execution Halted: Error in ${failedStep.label}` : 'Pipeline Execution Failed'}
                </Text>
                <Badge text="EXECUTION STOPPED" color={colors.danger} />
              </Row>
              <Text style={{ fontSize: 13, color: '#991B1B', marginTop: 4, lineHeight: 18 }}>
                Execution stopped immediately at this stage. All downstream pipeline steps were aborted to protect data integrity and avoid inconsistent scoping.
              </Text>

              <View style={{ marginTop: space(2), padding: space(2), backgroundColor: '#FFFFFF', borderRadius: 8, borderWidth: 1, borderColor: '#FCA5A5' }}>
                <Text style={{ fontSize: 11, fontWeight: '700', color: colors.danger, textTransform: 'uppercase', marginBottom: 2 }}>Error Message:</Text>
                <Text style={{ fontSize: 13, color: colors.text, fontFamily: 'monospace' }}>
                  {failedStep?.message || (r?.WARNINGS && r.WARNINGS[0]) || 'An unexpected error occurred during execution.'}
                </Text>
              </View>

              <View style={{ marginTop: space(2), flexDirection: 'row', gap: space(2) }}>
                {canRun ? <Button small kind="primary" title="Retry Pipeline Execution" onPress={start} /> : null}
              </View>
            </View>
          </Row>
        </Card>
      ) : null}

      {/* Stage-by-Stage Live Execution Tracker & Animation */}
      {steps && steps.length > 0 ? (
        <Card style={{ marginBottom: space(3), padding: space(3), borderColor: running ? colors.info : colors.border, borderWidth: 1, backgroundColor: colors.surfaceAlt }}>
          <Row style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: space(1.5) }}>
            <Row style={{ alignItems: 'center', gap: space(1) }}>
              {running ? <ActivityIndicator size="small" color={colors.info} /> : null}
              <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>
                {running && runningStep
                  ? `Stage ${runningIndex + 1} of ${totalSteps}: ${runningStep.label} (Running...)`
                  : isFailed
                  ? `Execution Stopped at Stage ${(steps.findIndex((s) => s.status === 'FAILED') + 1) || 1} of ${totalSteps}`
                  : `Pipeline Completed (${completedCount}/${totalSteps} Stages Successful)`}
              </Text>
            </Row>
            <Badge
              text={running ? `${progressPct}%` : isFailed ? 'STOPPED' : '100%'}
              color={running ? colors.info : isFailed ? colors.danger : colors.ok}
            />
          </Row>

          {/* Progress Bar Animation */}
          <View style={{ height: 8, backgroundColor: colors.border, borderRadius: 4, overflow: 'hidden', marginBottom: space(2) }}>
            <View
              style={{
                height: '100%',
                width: `${running ? Math.max(progressPct, ((runningIndex + 0.5) / totalSteps) * 100) : isFailed ? Math.max(progressPct, 15) : 100}%`,
                backgroundColor: isFailed ? colors.danger : running ? colors.info : colors.ok,
                borderRadius: 4,
              }}
            />
          </View>

          {/* Stage Sequence Stepper Chips */}
          <Row style={{ gap: space(1), flexWrap: 'wrap' }}>
            {steps.map((st, idx) => {
              const isDone = st.status === 'DONE';
              const isRunning = st.status === 'RUNNING';
              const isStepFailed = st.status === 'FAILED';
              const isAborted = isFailed && !isDone && !isStepFailed;

              return (
                <View
                  key={st.key}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    paddingHorizontal: 8,
                    paddingVertical: 4,
                    borderRadius: 6,
                    borderWidth: 1,
                    backgroundColor: isDone
                      ? '#E6F4EA'
                      : isRunning
                      ? '#E8F0FE'
                      : isStepFailed
                      ? '#FCE8E6'
                      : colors.surface,
                    borderColor: isDone
                      ? '#CEEAD6'
                      : isRunning
                      ? colors.info
                      : isStepFailed
                      ? colors.danger
                      : colors.border,
                  }}
                >
                  <Text
                    style={{
                      fontSize: 11,
                      fontWeight: '700',
                      color: isDone ? '#137333' : isRunning ? colors.info : isStepFailed ? colors.danger : isAborted ? colors.muted : colors.text,
                    }}
                  >
                    {isDone ? `✓ ${idx + 1}. ${st.label}` : isRunning ? `⏳ ${idx + 1}. ${st.label}` : isStepFailed ? `✕ ${idx + 1}. ${st.label}` : isAborted ? `⊘ ${idx + 1}. ${st.label}` : `○ ${idx + 1}. ${st.label}`}
                  </Text>
                </View>
              );
            })}
          </Row>
        </Card>
      ) : null}

      {!id ? (
        <View style={{ marginTop: space(2) }}>
          <Empty text="The pipeline has not run for this site yet. Tap 'Run Pipeline' above to execute." />
        </View>
      ) : null}
      {err ? <ErrorView error={err} /> : null}
      {run.error ? <ErrorView error={run.error} onRetry={run.reload} /> : null}
      {id && !r && !run.error ? <Loading /> : null}
      {r ? (
        <View style={{ marginTop: space(1) }}>
          <View style={{ marginTop: space(1) }}>
            {steps ? (
              <PipelineSteps runId={r.RUN_ID} siteId={siteId} steps={steps} onChanged={() => setVersion((v) => v + 1)} />
            ) : (
              <Empty text="This run was recorded before step tracking. Run the pipeline again to see its steps." />
            )}
          </View>
          {!running && !isFailed ? <ImplementChanges key={version} siteId={siteId} /> : null}
        </View>
      ) : null}
    </View>
  );
}
