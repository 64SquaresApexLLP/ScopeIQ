// "Review, then implement": shows how many redlines are approved and, on request, builds the next CD revision from
// the approved ones (background job with its own step progress). The result lists every redline as applied or not,
// with the reason, and links the revised drawing. Approving / rejecting redlines happens in the Redlines step or tab.
import React, { useState } from 'react';
import { Linking, View } from 'react-native';
import { api, ApiError, authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { when } from '../../lib/format';
import { PipelineRun, RevisionChange, Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, space } from '../theme';
import { Badge, Button, Card, ErrorView, Muted, Row, Section, Title } from '../ui';
import { PipelineSteps } from './PipelineSteps';

const APPROVED = ['APPROVED', 'SENT_TO_AE', 'ACKNOWLEDGED', 'INCORPORATED'];

export function ImplementChanges({ siteId }: { siteId: string }) {
  const { can } = useAuth();
  const redlines = useApi<R[]>(`/redlines?site_id=${siteId}`);
  const rev = useApi<{ job: PipelineRun | null; revision: PipelineRun | null }>(`/pipeline/sites/${siteId}/revision`, {
    pollMs: 1500, keepPolling: (d) => d.job?.STATUS === 'RUNNING',
  });
  const [err, setErr] = useState<ApiError | null>(null);

  const cd = (redlines.data ?? []).filter((r) => r.DOC_TYPE === 'CD');
  const approved = cd.filter((r) => APPROVED.includes(r.STATUS)).length;
  const waiting = cd.filter((r) => !APPROVED.includes(r.STATUS) && r.STATUS !== 'REJECTED').length;
  const job = rev.data?.job ?? null;
  const running = job?.STATUS === 'RUNNING';
  const done = rev.data?.revision ?? null;
  const steps = Array.isArray(job?.STEPS) ? job!.STEPS : [];
  const changes: RevisionChange[] = done?.SUMMARY?.changes ?? [];
  const files: Record<string, string> = done?.SUMMARY?.files ?? {};

  const implement = async () => {
    setErr(null);
    try {
      await api.post(`/pipeline/sites/${siteId}/apply`);
      await rev.reload();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  const open = (kind: string) => Linking.openURL(authedUrl(`/pipeline/runs/${done!.RUN_ID}/file/${kind}`));

  if (!cd.length && !redlines.loading) return null;           // nothing to implement: no drawing changes for this site
  return (
    <Section title="Review and implement changes">
      <Card>
        <Muted>Redlines are drafted from the findings. Approve the ones you accept, then implement them to produce the next drawing revision. Nothing changes in the drawing until you do.</Muted>
        <Row style={{ marginTop: space(2) }}>
          <Badge text={`${approved} approved`} color={approved ? colors.ok : colors.muted} />
          <Badge text={`${waiting} awaiting review`} color={waiting ? colors.warn : colors.muted} />
          <Badge text={`${cd.length} total`} color={colors.muted} />
        </Row>
        <View style={{ marginTop: space(3) }}>
          <Button title={running ? 'Implementing changes...' : 'Implement changes'} disabled={running || !approved || !can('REVIEWER', 'AE_ENGINEER', 'SCOPER')} onPress={implement} />
        </View>
        {!approved ? <Muted style={{ marginTop: space(2) }}>Approve at least one redline first (open the Redlines step above, or the Redlines and RFIs tab).</Muted> : null}
        {waiting && approved ? <Muted style={{ marginTop: space(2) }}>{`${waiting} redline(s) are not approved yet and will be listed as not applied.`}</Muted> : null}
        {err ? <View style={{ marginTop: space(2) }}><ErrorView error={err} /></View> : null}
      </Card>

      {steps.length ? (
        <View style={{ marginTop: space(2) }}>
          <Muted>{`Implement run started ${when(job!.STARTED_AT)} - ${job!.STATUS.replace(/_/g, ' ').toLowerCase()}`}</Muted>
          <PipelineSteps runId={job!.RUN_ID} siteId={siteId} steps={steps} detail={false} />
          {job!.STATUS === 'FAILED' ? <ErrorView error={new Error((job!.WARNINGS ?? [])[0] ?? 'The revision could not be built')} /> : null}
          {job!.STATUS === 'SUCCEEDED_WITH_WARNINGS' && !done ? <Muted>{(job!.WARNINGS ?? [])[0]}</Muted> : null}
        </View>
      ) : null}

      {done ? (
        <Card style={{ borderColor: colors.ok }}>
          <Row style={{ justifyContent: 'space-between' }}>
            <Title>{`Revised drawing (from ${done.SUMMARY?.from_revision ?? 'CD'})`}</Title>
            <Badge text={`${done.SUMMARY?.applied ?? 0} of ${changes.length} applied`} color={colors.ok} />
          </Row>
          <Muted>{`Built ${when(done.FINISHED_AT)}`}</Muted>
          <Row style={{ marginTop: space(2) }}>
            {files.revised_cd_pdf ? <Button small title="Open revised CD (PDF)" onPress={() => open('revised_cd_pdf')} /> : null}
            {files.revised_cd_dxf ? <Button small kind="secondary" title="Download DXF" onPress={() => open('revised_cd_dxf')} /> : null}
            {files.revised_cd_changes ? <Button small kind="secondary" title="Change log" onPress={() => open('revised_cd_changes')} /> : null}
          </Row>
          <Section title="What changed on the drawing">
            {changes.map((c) => (
              <View key={c.redline_id} style={{ paddingVertical: 4 }}>
                <Row style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
                  <Muted style={{ color: colors.text, flex: 1 }}>{`${c.sheet}: ${c.markup}`}</Muted>
                  <Badge text={c.applied ? 'APPLIED' : 'NOT APPLIED'} color={c.applied ? colors.ok : colors.warn} />
                </Row>
                {c.detail ? <Muted>{c.detail}</Muted> : null}
              </View>
            ))}
          </Section>
          <Muted style={{ marginTop: space(2) }}>When the A&E incorporates the redlines this drawing becomes the site's current CD; the next pipeline run reads it and the resolved findings close.</Muted>
        </Card>
      ) : null}
    </Section>
  );
}
