// Pipeline tab: what the backend does for this site, step by step, live while it runs. Each finished step opens to
// the rows it produced; the last section turns the approved redlines into the next drawing revision.
import React, { useEffect, useRef, useState } from 'react';
import { View } from 'react-native';
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
  const [started, setStarted] = useState<string | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [version, setVersion] = useState(0);               // bumped when a redline changes, so the approved count refreshes
  const id = started ?? latest.data?.RUN_ID ?? null;
  const run = useApi<PipelineRun>(id ? `/pipeline/runs/${id}` : null, { pollMs: 1500, keepPolling: (r) => r.STATUS === 'RUNNING' });

  // tell the site screen when a run finishes so the other tabs show the new results
  const was = useRef<string | undefined>(undefined);
  useEffect(() => {
    const now = run.data?.STATUS;
    if (was.current === 'RUNNING' && now && now !== 'RUNNING') onFinished?.();
    was.current = now;
  }, [run.data?.STATUS, onFinished]);

  const start = async () => {
    setErr(null);
    try {
      const r = await api.post<{ run_id: string }>(`/pipeline/sites/${siteId}/start`);
      setStarted(r.run_id);
      void run.reload();
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

  return (
    <View>
      <Muted>The pipeline reads the site's documents, compares them, builds the BOM and estimate and drafts the redlines. Tap a finished step to see what it produced.</Muted>
      {!id ? (
        <View style={{ marginTop: space(3) }}>
          <Empty text="The pipeline has not run for this site yet." />
          {canRun ? <Button title="Run pipeline" onPress={start} /> : null}
        </View>
      ) : null}
      {err ? <ErrorView error={err} /> : null}
      {run.error ? <ErrorView error={run.error} onRetry={run.reload} /> : null}
      {id && !r && !run.error ? <Loading /> : null}
      {r ? (
        <View style={{ marginTop: space(3) }}>
          <Card style={running ? { borderColor: colors.info } : undefined}>
            <Row style={{ justifyContent: 'space-between' }}>
              <Title>{running ? 'Running...' : 'Last run'}</Title>
              <Badge text={r.STATUS} />
            </Row>
            <KV k="Started" v={`${when(r.STARTED_AT)} by ${r.TRIGGERED_BY ?? '-'}`} />
            <KV k="Finished" v={r.FINISHED_AT ? when(r.FINISHED_AT) : 'in progress'} />
            <KV k="Run id" v={r.RUN_ID} />
            {(r.WARNINGS ?? []).slice(0, 5).map((w, i) => <Muted key={i} style={{ color: colors.warn }}>{w}</Muted>)}
            {running ? <Muted style={{ marginTop: space(2) }}>It keeps running on the server if you leave this screen.</Muted> : null}
            {canRun ? <View style={{ marginTop: space(3) }}><Button small kind="secondary" title={running ? 'Running...' : 'Re-run pipeline'} disabled={running} onPress={start} /></View> : null}
          </Card>
          <View style={{ marginTop: space(2) }}>
            {steps ? (
              <PipelineSteps runId={r.RUN_ID} siteId={siteId} steps={steps} onChanged={() => setVersion((v) => v + 1)} />
            ) : (
              <Empty text="This run was recorded before step tracking. Run the pipeline again to see its steps." />
            )}
          </View>
          {!running ? <ImplementChanges key={version} siteId={siteId} /> : null}
        </View>
      ) : null}
    </View>
  );
}
