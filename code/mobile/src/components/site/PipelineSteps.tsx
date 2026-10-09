// Step-by-step view of a pipeline run: status and timing per phase (live while it runs), and, for a finished phase,
// the rows it produced - documents, extracted values, findings, equipment delta, BOM, estimate, redlines and RFIs.
import { router } from 'expo-router';
import React, { useState } from 'react';
import { ActivityIndicator, Linking, Pressable, Text, View } from 'react-native';
import { authedUrl } from '../../lib/api';
import { label, money, num, SECTOR, show } from '../../lib/format';
import { PipelineStep, Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, space } from '../theme';
import { Badge, Button, Card, Empty, ErrorView, KV, Loading, Muted, Row, Section, Stat, Title } from '../ui';
import { WorkflowActions } from '../WorkflowActions';
import { Delta } from './Delta';

const seconds = (ms: number | null) => (ms == null ? '' : ms < 950 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`);

function Marker({ status }: { status: PipelineStep['status'] }) {
  if (status === 'RUNNING') return <ActivityIndicator size="small" color={colors.info} />;
  const [glyph, color] = status === 'DONE' ? ['✓', colors.ok] : status === 'FAILED' ? ['✕', colors.danger] : ['○', colors.border];
  return <Text style={{ width: 20, textAlign: 'center', fontSize: 16, fontWeight: '800', color }}>{glyph}</Text>;
}

/** All steps of a run; `detail` renders what a finished step produced (omit for jobs whose steps have no detail view). */
export function PipelineSteps({ runId, siteId, steps, detail = true, onChanged }: { runId: string; siteId: string; steps: PipelineStep[]; detail?: boolean; onChanged?: () => void }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <View>
      {steps.map((st, i) => {
        const can = detail && (st.status === 'DONE' || st.status === 'FAILED') && st.key !== 'PERSIST';
        const isOpen = open === st.key;
        return (
          <Card key={st.key} style={st.status === 'FAILED' ? { borderColor: colors.danger } : st.status === 'RUNNING' ? { borderColor: colors.info } : undefined}>
            <Pressable disabled={!can} onPress={() => setOpen(isOpen ? null : st.key)} accessibilityRole="button" accessibilityLabel={`${st.label}, ${st.status}`}>
              <Row style={{ flexWrap: 'nowrap' }}>
                <Marker status={st.status} />
                <View style={{ flex: 1 }}>
                  <Row style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
                    <Title style={st.status === 'PENDING' ? { color: colors.muted } : undefined}>{`${i + 1}. ${st.label}`}</Title>
                    <Muted>{st.status === 'RUNNING' ? 'running...' : seconds(st.duration_ms)}</Muted>
                  </Row>
                  {st.message ? <Muted style={st.status === 'FAILED' ? { color: colors.danger } : undefined}>{st.message}</Muted> : null}
                </View>
                {can ? <Text style={{ color: colors.muted, fontSize: 18 }}>{isOpen ? '▾' : '▸'}</Text> : null}
              </Row>
            </Pressable>
            {isOpen ? <View style={{ marginTop: space(3) }}><StepDetail runId={runId} siteId={siteId} stepKey={st.key} onChanged={onChanged} /></View> : null}
          </Card>
        );
      })}
    </View>
  );
}

function StepDetail({ runId, siteId, stepKey, onChanged }: { runId: string; siteId: string; stepKey: string; onChanged?: () => void }) {
  const d = useApi<any>(`/pipeline/runs/${runId}/steps/${stepKey}`);
  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading />;
  const x = d.data;
  switch (stepKey) {
    case 'INGEST': return <Documents rows={x.documents} />;
    case 'EXTRACT': return <Extracted x={x} />;
    case 'RECONCILE': return <Findings rows={x.discrepancies} />;
    case 'DELTA': return <Delta rows={x.delta} />;
    case 'GENERATE': return <Bom x={x} />;
    case 'ESTIMATE': return <Estimate x={x} />;
    case 'REDLINES': return <RedlinesAndRfis siteId={siteId} x={x} reload={() => { void d.reload(); onChanged?.(); }} />;
    case 'FILES': return <Files files={x.files} />;
    default: return <Empty text="Nothing to show for this step." />;
  }
}

function Documents({ rows }: { rows: R[] }) {
  if (!rows.length) return <Empty text="No documents found for this site." />;
  return (
    <View>
      {rows.map((r) => (
        <Row key={r.DOC_ID} style={{ justifyContent: 'space-between', paddingVertical: 4 }}>
          <View style={{ flex: 1 }}>
            <Muted style={{ color: colors.text }}>{r.FILE_NAME}</Muted>
            <Muted>{`${r.DOC_TYPE}${r.REVISION ? ` ${r.REVISION}` : ''} - ${Math.round((r.SIZE_BYTES ?? 0) / 1024)} KB${r.SOURCE === 'upload' ? ' - uploaded' : ''}`}</Muted>
          </View>
          <Badge text={r.STATUS} color={r.STATUS === 'CURRENT' ? colors.ok : colors.muted} />
        </Row>
      ))}
    </View>
  );
}

function Extracted({ x }: { x: { total: number; needs_review: number; fields: R[]; config_lines: R[] } }) {
  return (
    <View>
      <Row>
        <Stat label="Values read" value={x.total} />
        <Stat label="Need review" value={x.needs_review} color={x.needs_review ? colors.warn : undefined} />
        <Stat label="Equipment lines" value={x.config_lines.length} />
      </Row>
      <Section title={x.needs_review ? 'Low confidence first' : 'Values'}>
        {x.fields.slice(0, 25).map((f) => (
          <Row key={f.FIELD_ID} style={{ justifyContent: 'space-between', paddingVertical: 3 }}>
            <View style={{ flex: 1 }}>
              <Muted style={{ color: colors.text }}>{`${f.FIELD_NAME} = ${show(f.VALUE)}`}</Muted>
              <Muted>{`${f.METHOD ?? ''}${f.PAGE ? ` - ${f.PAGE}` : ''}`}</Muted>
            </View>
            <Badge text={`${Math.round((f.CONFIDENCE ?? 0) * 100)}%`} color={f.NEEDS_REVIEW ? colors.warn : colors.ok} />
          </Row>
        ))}
        {x.total > 25 ? <Muted>{`...and ${x.total - 25} more`}</Muted> : null}
      </Section>
    </View>
  );
}

function Findings({ rows }: { rows: R[] }) {
  if (!rows.length) return <Empty text="No findings: the sources agree." />;
  return (
    <View>
      {rows.map((x) => (
        <Card key={x.DISC_ID} onPress={() => router.push({ pathname: '/discrepancy/[id]', params: { id: x.DISC_ID } })} style={{ marginBottom: space(2) }}>
          <Row style={{ justifyContent: 'space-between' }}><Title>{x.RULE_ID}</Title><Row><Badge text={x.SEVERITY} /><Badge text={x.STATUS} /></Row></Row>
          <Muted style={{ color: colors.text }}>{x.TITLE}</Muted>
          <Row style={{ marginTop: space(1) }}>
            <Badge text={x.OUTCOME} color={colors.primary} />
            {x.SECTOR ? <Badge text={`Sector ${x.SECTOR}${x.POSITION ? ` pos ${x.POSITION}` : ''}`} color={colors.muted} /> : null}
          </Row>
        </Card>
      ))}
    </View>
  );
}

function Bom({ x }: { x: { revision: R | null; changes: R[]; lines: number } }) {
  if (!x.revision) return <Empty text="No BOM was generated." />;
  const r = x.revision;
  return (
    <View>
      <Row style={{ justifyContent: 'space-between' }}><Title>{r.REV_LABEL}</Title><Badge text={r.STATUS} /></Row>
      <Muted>{`${x.lines} lines, ${x.changes.length} change(s) against REV 0`}</Muted>
      <Section title="Changes vs REV 0">
        {x.changes.map((c) => (
          <View key={c.CHANGE_ID} style={{ paddingVertical: 4 }}>
            <Row style={{ justifyContent: 'space-between' }}><Muted style={{ color: colors.text }}>{`${SECTOR[c.SECTOR] ?? c.SECTOR}: ${c.CATALOG_KEY}`}</Muted><Badge text={c.ACTION} /></Row>
            <Muted>{`REV 0 ${num(c.FROM_QTY)} -> ${num(c.TO_QTY)}  ${(c.REASONS ?? []).map((q: R) => q.reason_code).join(', ')}`}</Muted>
          </View>
        ))}
        {!x.changes.length ? <Muted>The generated BOM equals REV 0.</Muted> : null}
      </Section>
      <View style={{ marginTop: space(2) }}>
        <Button small kind="secondary" title="Open BOM revision" onPress={() => router.push({ pathname: '/bom/[revId]', params: { revId: r.BOM_REV_ID } })} />
      </View>
    </View>
  );
}

function Estimate({ x }: { x: { estimate: R | null; drivers: R[]; requirements: R | null } }) {
  const e = x.estimate;
  return (
    <View>
      <Row>
        <Stat label="Cycle days" value={num(e?.CYCLE_DAYS)} />
        <Stat label="Services" value={money(e?.SERVICES_USD)} />
        <Stat label="Material" value={money(e?.MATERIAL_USD)} />
        <Stat label="Total" value={money(e?.TOTAL_USD)} />
      </Row>
      {x.requirements ? (
        <Section title="Access and rigging">
          <KV k="Access" v={label(x.requirements.ACCESS_METHOD)} />
          <KV k="Crane / manlift days" v={`${num(x.requirements.CRANE_DAYS)} / ${num(x.requirements.MANLIFT_DAYS)}`} />
          <KV k="Hold" v={x.requirements.HOLD ? 'YES - structure or RFI blocks construction' : 'No'} />
        </Section>
      ) : null}
      <Section title={`Service drivers (${x.drivers.length})`}>
        {x.drivers.map((d) => (
          <Row key={d.LINE_ID} style={{ justifyContent: 'space-between', paddingVertical: 3 }}>
            <View style={{ flex: 1 }}><Muted style={{ color: colors.text }}>{d.DRIVER_CODE}</Muted><Muted numberOfLines={1}>{`${d.DESCRIPTION} - ${num(d.QTY)} ${d.UOM}`}</Muted></View>
            <Muted style={{ color: colors.text }}>{money(d.AMOUNT)}</Muted>
          </Row>
        ))}
      </Section>
    </View>
  );
}

/** Redlines drafted by the run with their Was/Now; approve or reject them here, then implement the approved ones. */
function RedlinesAndRfis({ siteId, x, reload }: { siteId: string; x: { redlines: R[]; rfis: R[] }; reload: () => void }) {
  const live = useApi<R[]>(`/redlines?site_id=${siteId}`);        // carries the role-specific workflow buttons and the PDF link
  const redlines = live.data ?? x.redlines;
  const pdf = redlines.find((r) => r.PDF_PATH)?.PDF_PATH;
  return (
    <View>
      {pdf ? <Button small kind="secondary" title="Open red-marked CD (PDF)" onPress={() => Linking.openURL(authedUrl(`/files/${pdf}`))} /> : null}
      <Section title={`Redlines (${redlines.length})`}>
        {!redlines.length ? <Muted>No drawing changes are needed.</Muted> : null}
        {redlines.map((r, i) => <RedlineCard key={r.REDLINE_ID} r={r} n={i + 1} reload={() => { void live.reload(); reload(); }} />)}
      </Section>
      <Section title={`RFIs (${x.rfis.length})`}>
        {!x.rfis.length ? <Muted>No questions to raise.</Muted> : null}
        {x.rfis.map((r) => (
          <View key={r.RFI_ID} style={{ paddingVertical: 4 }}>
            <Row style={{ justifyContent: 'space-between' }}><Muted style={{ color: colors.text }}>{`To ${r.TO_PARTY}`}</Muted><Badge text={r.STATUS} /></Row>
            <Muted>{r.SUBJECT}</Muted>
          </View>
        ))}
      </Section>
    </View>
  );
}

function RedlineCard({ r, n, reload }: { r: R; n: number; reload: () => void }) {
  return (
    <Card style={{ marginBottom: space(2) }}>
      <Row style={{ justifyContent: 'space-between' }}><Title>{`${n}. ${r.DOC_TYPE} ${r.DOC_REVISION ?? ''} sheet ${r.SHEET}`}</Title><Badge text={r.STATUS} /></Row>
      <Muted style={{ color: colors.text }}>{r.MARKUP}</Muted>
      <KV k="Was" v={r.CHANGE_FROM} />
      <KV k="Now" v={r.CHANGE_TO} />
      {r.ACTIONS ? (
        <View style={{ marginTop: space(2) }}>
          <WorkflowActions actions={r.ACTIONS} endpoint={`/redlines/${r.REDLINE_ID}/transition`} entity="REDLINE" onDone={reload} />
        </View>
      ) : null}
    </Card>
  );
}

function Files({ files }: { files: Record<string, string> }) {
  const rows = Object.entries(files ?? {});
  if (!rows.length) return <Empty text="No files were written." />;
  return (
    <View>
      {rows.map(([k, rel]) => (
        <Row key={k} style={{ justifyContent: 'space-between', paddingVertical: 4 }}>
          <View style={{ flex: 1 }}><Muted style={{ color: colors.text }}>{label(k)}</Muted><Muted numberOfLines={1}>{rel}</Muted></View>
          <Button small kind="secondary" title="Open" onPress={() => Linking.openURL(authedUrl(`/files/${rel}`))} />
        </Row>
      ))}
    </View>
  );
}
