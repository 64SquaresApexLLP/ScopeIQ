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

function Marker({ status, isAborted }: { status: PipelineStep['status']; isAborted?: boolean }) {
  if (status === 'RUNNING') {
    return (
      <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: '#E8F0FE', alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator size="small" color={colors.info} />
      </View>
    );
  }
  if (status === 'DONE') {
    return (
      <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: '#E6F4EA', alignItems: 'center', justifyContent: 'center' }}>
        <Text style={{ fontSize: 13, fontWeight: '800', color: '#137333' }}>✓</Text>
      </View>
    );
  }
  if (status === 'FAILED') {
    return (
      <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: '#FCE8E6', alignItems: 'center', justifyContent: 'center' }}>
        <Text style={{ fontSize: 13, fontWeight: '800', color: colors.danger }}>✕</Text>
      </View>
    );
  }
  if (isAborted) {
    return (
      <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: '#F1F3F4', alignItems: 'center', justifyContent: 'center' }}>
        <Text style={{ fontSize: 13, fontWeight: '800', color: colors.muted }}>⊘</Text>
      </View>
    );
  }
  return (
    <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: colors.surfaceAlt, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border }}>
      <Text style={{ fontSize: 11, fontWeight: '700', color: colors.muted }}>○</Text>
    </View>
  );
}

/** All steps of a run; `detail` renders what a finished step produced (omit for jobs whose steps have no detail view). */
export function PipelineSteps({ runId, siteId, steps, detail = true, onChanged }: { runId: string; siteId: string; steps: PipelineStep[]; detail?: boolean; onChanged?: () => void }) {
  // Default open Stage 1 (INGEST) and Stage 2 (EXTRACT) so scoper sees documents and parallel extraction cards immediately
  const [openMap, setOpenMap] = useState<Record<string, boolean>>({ INGEST: true, EXTRACT: true });

  const hasFailed = steps.some((s) => s.status === 'FAILED');
  const failedIndex = steps.findIndex((s) => s.status === 'FAILED');

  // Auto-expand active running step or failed step so user sees what is happening
  React.useEffect(() => {
    const active = steps.find((s) => s.status === 'RUNNING' || s.status === 'FAILED');
    if (active) {
      setOpenMap((prev) => ({ ...prev, [active.key]: true }));
    }
  }, [steps]);

  const toggle = (key: string) => {
    setOpenMap((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <View>
      {steps.map((st, i) => {
        const isRunning = st.status === 'RUNNING';
        const isStepFailed = st.status === 'FAILED';
        const isAborted = hasFailed && i > failedIndex;
        const can = detail && (st.status === 'DONE' || isStepFailed) && st.key !== 'PERSIST';
        const isOpen = !!openMap[st.key];

        return (
          <Card
            key={st.key}
            style={{
              marginBottom: space(2),
              ...(isStepFailed
                ? { borderColor: colors.danger, borderWidth: 2, backgroundColor: '#FFFDFD' }
                : isRunning
                ? { borderColor: colors.info, borderWidth: 2, backgroundColor: '#F8FAFF' }
                : isAborted
                ? { opacity: 0.7 }
                : {}),
            }}
          >
            <Pressable disabled={!can} onPress={() => toggle(st.key)} accessibilityRole="button" accessibilityLabel={`${st.label}, ${st.status}`}>
              <Row style={{ flexWrap: 'nowrap', alignItems: 'center' }}>
                <Marker status={st.status} isAborted={isAborted} />
                <View style={{ flex: 1, marginLeft: space(2) }}>
                  <Row style={{ justifyContent: 'space-between', flexWrap: 'nowrap', alignItems: 'center' }}>
                    <Row style={{ alignItems: 'center', gap: space(1) }}>
                      <Title style={st.status === 'PENDING' ? { color: colors.muted } : isStepFailed ? { color: colors.danger } : undefined}>
                        {`Stage ${i + 1}: ${st.label}`}
                      </Title>
                      {isRunning ? <Badge text="RUNNING..." color={colors.info} /> : isStepFailed ? <Badge text="FAILED" color={colors.danger} /> : isAborted ? <Badge text="ABORTED" color={colors.muted} /> : null}
                    </Row>
                    <Muted>{isRunning ? 'Processing...' : seconds(st.duration_ms)}</Muted>
                  </Row>

                  {/* Stage-by-stage live progress explanation */}
                  {isRunning ? (
                    <View style={{ marginTop: 4 }}>
                      <Muted style={{ color: colors.info, fontSize: 12 }}>
                        {i === 0 ? 'Intaking site engineering documents and checking revision ranks...' : i === 1 ? 'Extracting LiDAR point cloud & CAD drawing vectors in parallel...' : 'Processing consistency rules and engineering checks...'}
                      </Muted>
                    </View>
                  ) : null}

                  {st.message && !isStepFailed ? <Muted>{st.message}</Muted> : null}

                  {isAborted ? (
                    <Muted style={{ color: colors.muted, fontSize: 12, marginTop: 2 }}>
                      Execution stopped: Stage skipped due to failure in Stage {failedIndex + 1}.
                    </Muted>
                  ) : null}
                </View>
                {can ? <Text style={{ color: isStepFailed ? colors.danger : colors.primary, fontSize: 18, fontWeight: '700', paddingLeft: space(2) }}>{isOpen ? '▾' : '▸'}</Text> : null}
              </Row>
            </Pressable>

            {/* Stage failure alert with exact error message */}
            {isStepFailed ? (
              <View style={{ marginTop: space(2), padding: space(2.5), backgroundColor: '#FEF2F2', borderRadius: 8, borderWidth: 1, borderColor: '#FCA5A5' }}>
                <Row style={{ alignItems: 'center', gap: space(1), marginBottom: 4 }}>
                  <Text style={{ fontSize: 16 }}>⚠️</Text>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: colors.danger }}>Stage Error (Execution Halted)</Text>
                </Row>
                <Text style={{ fontSize: 13, color: colors.text, fontFamily: 'monospace' }}>
                  {st.message || 'Error occurred while executing this stage.'}
                </Text>
                <Text style={{ fontSize: 11, color: colors.danger, marginTop: 4 }}>
                  Subsequent stages were halted to protect data integrity.
                </Text>
              </View>
            ) : null}

            {isOpen ? (
              <View style={{ marginTop: space(3), paddingTop: space(2), borderTopWidth: 1, borderTopColor: colors.border }}>
                <StepDetail key={`${runId}-${st.key}-${st.status}`} runId={runId} siteId={siteId} stepKey={st.key} stepStatus={st.status} onChanged={onChanged} />
              </View>
            ) : null}
          </Card>
        );
      })}
    </View>
  );
}

function StepDetail({ runId, siteId, stepKey, stepStatus, onChanged }: { runId: string; siteId: string; stepKey: string; stepStatus: string; onChanged?: () => void }) {
  const d = useApi<any>(
    `/pipeline/runs/${runId}/steps/${stepKey}`,
    stepStatus === 'RUNNING' ? { pollMs: 1500, keepPolling: (data) => !data || !data.total } : undefined
  );
  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading />;
  const x = d.data;
  switch (stepKey) {
    case 'INGEST': return <Documents data={x} rows={x.documents ?? []} />;
    case 'EXTRACT': return <Extracted x={x} isRunning={stepStatus === 'RUNNING'} />;
    case 'RECONCILE': return <Findings rows={x.discrepancies} />;
    case 'DELTA': return <Delta rows={x.delta} />;
    case 'GENERATE': return <Bom x={x} />;
    case 'ESTIMATE': return <Estimate x={x} />;
    case 'REDLINES': return <RedlinesAndRfis siteId={siteId} x={x} reload={() => { void d.reload(); onChanged?.(); }} />;
    case 'FILES': return <Files files={x.files} />;
    default: return <Empty text="Nothing to show for this step." />;
  }
}

function Documents({ data, rows }: { data?: any; rows: R[] }) {
  const items = rows || data?.documents || [];
  if (!items.length) return <Empty text="No documents found for this site." />;
  const formats: string[] = data?.formats ?? Array.from(new Set(items.map((r: R) => r.FILE_FORMAT).filter(Boolean)));
  const currentCount = data?.current_count ?? items.filter((r: R) => r.STATUS === 'CURRENT').length;
  const supersededCount = data?.superseded_count ?? items.filter((r: R) => r.STATUS === 'SUPERSEDED').length;

  return (
    <View>
      <Row style={{ marginBottom: space(2) }}>
        <Stat label="Total Ingested" value={items.length} />
        <Stat label="Active Current" value={currentCount} color={colors.ok} />
        {supersededCount > 0 ? <Stat label="Superseded" value={supersededCount} color={colors.muted} /> : null}
      </Row>

      <View style={{ marginBottom: space(2), padding: space(2), backgroundColor: colors.surfaceAlt, borderRadius: 8, borderWidth: 1, borderColor: colors.border }}>
        <Muted style={{ fontWeight: '700', color: colors.text, marginBottom: space(1) }}>Detected Document Formats:</Muted>
        <Row style={{ gap: space(1) }}>
          {formats.map((fmt) => (
            <Badge key={fmt} text={`.${fmt.toUpperCase()}`} color={colors.primary} />
          ))}
        </Row>
      </View>

      <Section title={`Ingested Files (${items.length})`}>
        {items.map((r: R) => (
          <Row key={r.DOC_ID} style={{ justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border }}>
            <View style={{ flex: 1 }}>
              <Row style={{ alignItems: 'center', gap: space(1) }}>
                <Muted style={{ color: colors.text, fontWeight: '600' }}>{r.FILE_NAME}</Muted>
                {r.FILE_FORMAT ? <Badge text={`.${r.FILE_FORMAT}`} color={colors.muted} /> : null}
              </Row>
              <Muted>{`${r.DOC_TYPE}${r.REVISION ? ` ${r.REVISION}` : ''} • ${Math.round((r.SIZE_BYTES ?? 0) / 1024)} KB${r.SOURCE === 'upload' ? ' • Uploaded' : ' • SharePoint Store'}`}</Muted>
            </View>
            <Badge
              text={r.STATUS === 'CURRENT' ? (r.REVISION ? `${r.REVISION} (LATEST)` : 'CURRENT') : 'SUPERSEDED'}
              color={r.STATUS === 'CURRENT' ? colors.ok : colors.muted}
            />
          </Row>
        ))}
      </Section>
    </View>
  );
}

function DroneDataCard({ drone, isRunning }: { drone: any; isRunning?: boolean }) {
  // detected_formats: real per-file format check returned by backend
  const detectedFormats: Array<{ format: string; doc_type: string; file_name: string; size_kb: number | null; on_disk: boolean }> =
    drone.detected_formats ?? [];

  // identified_objects: actual objects extracted from the .laz point cloud, stored in DB
  const identifiedObjects: Array<{
    object_id: string; object_type: string; sector: string | null; position: number | null;
    center_height_ft: number | null; facing_az_deg: number | null; bearing_deg: number | null;
    model_guess: string; confidence: number | null; route_length_ft: number | null; method: string;
  }> = drone.identified_objects ?? [];

  const objTypeCounts: Record<string, number> = drone.obj_type_counts ?? {};

  return (
    <Card style={{ flex: 1, minWidth: 320, borderColor: colors.info, borderWidth: 1.5 }}>
      <Row style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: space(2) }}>
        <Title style={{ fontSize: 16 }}>🛰️ Extraction of Drone Data</Title>
        <Badge
          text={isRunning ? 'EXTRACTION IN PROGRESS...' : (drone.method ?? 'DRONE EXTRACTION')}
          color={colors.info}
        />
      </Row>

      {/* In-progress status banner */}
      {isRunning ? (
        <View style={{ marginBottom: space(2), padding: space(2), backgroundColor: '#E8F0FE', borderRadius: 8, borderWidth: 1, borderColor: colors.info }}>
          <Row style={{ alignItems: 'center', gap: space(1) }}>
            <ActivityIndicator size="small" color={colors.info} />
            <Text style={{ fontSize: 13, fontWeight: '700', color: colors.info }}>Processing Drone Point Cloud...</Text>
          </Row>
        </View>
      ) : null}

      {/* 1. Data Format Check — real detected formats from backend (dynamic) */}
      <View style={{ marginBottom: space(2), padding: space(2), backgroundColor: colors.surfaceAlt, borderRadius: 8 }}>
        <Muted style={{ fontWeight: '700', color: colors.text, marginBottom: 6 }}>1. Data Format Check</Muted>
        {detectedFormats.length > 0 ? (
          detectedFormats.map((df, idx) => (
            <Row key={idx} style={{ justifyContent: 'space-between', alignItems: 'center', paddingVertical: 4,
              borderBottomWidth: idx < detectedFormats.length - 1 ? 1 : 0, borderBottomColor: colors.border }}>
              <Row style={{ alignItems: 'center', gap: space(1), flex: 1, flexWrap: 'wrap' }}>
                <Badge text={`.${df.format}`} color={df.on_disk ? colors.info : colors.warn} />
                <Muted style={{ fontSize: 12, flex: 1 }} numberOfLines={1}>{df.file_name}</Muted>
              </Row>
              <Muted style={{ fontSize: 11 }}>{df.size_kb != null ? `${df.size_kb} KB` : df.on_disk ? 'On disk' : 'Registered'}</Muted>
            </Row>
          ))
        ) : (drone.formats ?? []).length > 0 ? (
          <Row style={{ gap: space(1), flexWrap: 'wrap' }}>
            {(drone.formats ?? []).map((fmt: string) => (
              <Badge key={fmt} text={`.${fmt}`} color={colors.info} />
            ))}
          </Row>
        ) : (
          <Muted style={{ fontSize: 12 }}>No drone files detected yet.</Muted>
        )}
      </View>

      {/* 2. Identified Objects (from .laz LiDAR — dynamic, stored in CORE.FIELD_OBJECT) */}
      <View style={{ padding: space(2), backgroundColor: colors.surfaceAlt, borderRadius: 8 }}>
        <Row style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: space(1) }}>
          <Muted style={{ fontWeight: '700', color: colors.text }}>2. Identified Objects</Muted>
          <Badge text={`${identifiedObjects.length} total`} color={colors.info} />
        </Row>

        {/* Object type summary row */}
        {Object.keys(objTypeCounts).length > 0 ? (
          <Row style={{ gap: space(1), flexWrap: 'wrap', marginBottom: space(1.5) }}>
            {Object.entries(objTypeCounts).map(([type, count]) => (
              <Badge key={type} text={`${type}: ${count}`} color={colors.muted} />
            ))}
          </Row>
        ) : null}

        {identifiedObjects.length > 0 ? (
          <>
            {/* Table header */}
            <View style={{ flexDirection: 'row', paddingVertical: 4, borderBottomWidth: 2, borderBottomColor: colors.border, marginBottom: 2 }}>
              <Muted style={{ flex: 2, fontWeight: '700', fontSize: 11 }}>Object / Model</Muted>
              <Muted style={{ width: 56, fontWeight: '700', fontSize: 11, textAlign: 'center' }}>Sector</Muted>
              <Muted style={{ width: 52, fontWeight: '700', fontSize: 11, textAlign: 'center' }}>Ht (ft)</Muted>
              <Muted style={{ width: 48, fontWeight: '700', fontSize: 11, textAlign: 'center' }}>Conf</Muted>
            </View>
            {identifiedObjects.map((obj, idx) => (
              <View key={obj.object_id ?? idx} style={{ flexDirection: 'row', paddingVertical: 5,
                borderBottomWidth: idx < identifiedObjects.length - 1 ? 1 : 0, borderBottomColor: colors.border }}>
                <View style={{ flex: 2 }}>
                  <Muted style={{ fontWeight: '600', color: colors.text, fontSize: 12 }}>
                    {obj.object_type}{obj.model_guess ? ` — ${obj.model_guess}` : ''}
                  </Muted>
                  {obj.facing_az_deg != null ? (
                    <Muted style={{ fontSize: 11 }}>{`Az ${obj.facing_az_deg}°${obj.route_length_ft != null ? ` • Route ${obj.route_length_ft} ft` : ''}`}</Muted>
                  ) : obj.route_length_ft != null ? (
                    <Muted style={{ fontSize: 11 }}>{`Route ${obj.route_length_ft} ft`}</Muted>
                  ) : null}
                </View>
                <Muted style={{ width: 56, textAlign: 'center', fontSize: 12 }}>
                  {obj.sector ? `${obj.sector}${obj.position != null ? `-P${obj.position}` : ''}` : '—'}
                </Muted>
                <Muted style={{ width: 52, textAlign: 'center', fontSize: 12 }}>
                  {obj.center_height_ft != null ? obj.center_height_ft : '—'}
                </Muted>
                <View style={{ width: 48, alignItems: 'center' }}>
                  <Badge
                    text={obj.confidence != null ? `${Math.round(obj.confidence * 100)}%` : '—'}
                    color={obj.confidence != null && obj.confidence >= 0.8 ? colors.ok : colors.warn}
                  />
                </View>
              </View>
            ))}

          </>
        ) : isRunning ? (
          <Muted style={{ fontSize: 12 }}>Identifying objects from point cloud...</Muted>
        ) : (
          <Muted style={{ fontSize: 12 }}>No objects identified. Ensure a .laz file is available for this site.</Muted>
        )}
      </View>
    </Card>
  );
}

// Plain-language labels for the equipment read from the drawings
const CD_KIND: Record<string, string> = { passive: 'Antenna', air: 'Active antenna (AAU)', radio: 'Radio', pipe: 'Mount pipe', sled: 'Roof sled' };
const CD_STATUS: Record<string, string> = { Existing: 'Existing', New: 'New', Remove: 'Remove' };
const CD_PLURAL: Record<string, string> = { passive: 'Antennas', air: 'Active antennas (AAU)', radio: 'Radios', pipe: 'Mount pipes', sled: 'Roof sleds' };
const CD_ORDER = ['passive', 'air', 'radio', 'pipe', 'sled'];
const CD_PREVIEW_ROWS = 8;
const cdRank = (k: string) => { const i = CD_ORDER.indexOf(k); return i < 0 ? 99 : i; };

function CdDataCard({ cd, isRunning }: { cd: any; isRunning?: boolean }) {
  const detectedFormats: Array<{ format: string; file_name: string; size_kb: number | null; on_disk: boolean; revision: string; status: string }> = cd.detected_formats ?? [];
  const items: R[] = [...(cd.items ?? [])].sort((a, b) => cdRank(a.KIND) - cdRank(b.KIND) || String(a.SECTOR).localeCompare(String(b.SECTOR)) || (a.POSITION ?? 0) - (b.POSITION ?? 0));
  const counts: Record<string, number> = {};
  for (const it of items) { const k = CD_PLURAL[it.KIND] ?? 'Other'; counts[k] = (counts[k] ?? 0) + 1; }
  const main = items.filter((it) => it.KIND !== 'pipe' && it.KIND !== 'sled');
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? main : main.slice(0, CD_PREVIEW_ROWS);
  const how = String(cd.method ?? '').startsWith('DXF') ? 'Read from the CAD file' : 'Read from the drawing sheets';

  return (
    <Card style={{ flex: 1, minWidth: 320, borderColor: colors.primary, borderWidth: 1.5 }}>
      <Row style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: space(2) }}>
        <Title style={{ fontSize: 16 }}>📐 Extraction of CD Drawing Data</Title>
        <Row style={{ gap: space(1) }}>
          <Badge text={cd.revision ?? 'REV 1'} color={colors.ok} />
          <Badge text={isRunning ? 'EXTRACTION IN PROGRESS...' : how} color={colors.primary} />
        </Row>
      </Row>

      {isRunning ? (
        <View style={{ marginBottom: space(2), padding: space(2), backgroundColor: '#EFF6FF', borderRadius: 8, borderWidth: 1, borderColor: colors.primary }}>
          <Row style={{ alignItems: 'center', gap: space(1) }}>
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={{ fontSize: 13, fontWeight: '700', color: colors.primary }}>Reading the construction drawings...</Text>
          </Row>
        </View>
      ) : null}

      {/* 1. Data Format Check: the real drawing files found for this site */}
      <View style={{ marginBottom: space(2), padding: space(2), backgroundColor: colors.surfaceAlt, borderRadius: 8 }}>
        <Muted style={{ fontWeight: '700', color: colors.text, marginBottom: 6 }}>1. Data Format Check</Muted>
        {detectedFormats.length > 0 ? (
          detectedFormats.map((df, idx) => {
            const used = df.status === 'CURRENT' || !df.status;
            return (
              <Row key={idx} style={{ justifyContent: 'space-between', alignItems: 'center', paddingVertical: 4, borderBottomWidth: idx < detectedFormats.length - 1 ? 1 : 0, borderBottomColor: colors.border }}>
                <Row style={{ alignItems: 'center', gap: space(1), flex: 1, flexWrap: 'wrap' }}>
                  <Badge text={`.${df.format}`} color={used ? colors.primary : colors.muted} />
                  <Muted style={{ fontSize: 12, flex: 1 }} numberOfLines={1}>{df.file_name}</Muted>
                </Row>
                <Muted style={{ fontSize: 11 }}>{used ? (df.size_kb != null ? `${df.size_kb} KB` : 'Registered') : (df.status === 'SUPERSEDED' ? 'Older revision' : 'Not used')}</Muted>
              </Row>
            );
          })
        ) : (
          <Muted style={{ fontSize: 12 }}>No drawing files detected yet.</Muted>
        )}
      </View>

      {/* 2. Extracted CD Drawing Data: same layout as the drone card */}
      <View style={{ padding: space(2), backgroundColor: colors.surfaceAlt, borderRadius: 8 }}>
        <Row style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: space(1) }}>
          <Muted style={{ fontWeight: '700', color: colors.text }}>2. Extracted CD Drawing Data</Muted>
          <Badge text={`${items.length} total`} color={colors.primary} />
        </Row>

        {Object.keys(counts).length > 0 ? (
          <Row style={{ gap: space(1), flexWrap: 'wrap', marginBottom: space(1.5) }}>
            {Object.entries(counts).map(([type, count]) => <Badge key={type} text={`${type}: ${count}`} color={colors.muted} />)}
          </Row>
        ) : null}

        {shown.length > 0 ? (
          <>
            <View style={{ flexDirection: 'row', paddingVertical: 4, borderBottomWidth: 2, borderBottomColor: colors.border, marginBottom: 2 }}>
              <Muted style={{ flex: 2, fontWeight: '700', fontSize: 11 }}>Equipment / Model</Muted>
              <Muted style={{ width: 56, fontWeight: '700', fontSize: 11, textAlign: 'center' }}>Sector</Muted>
              <Muted style={{ width: 52, fontWeight: '700', fontSize: 11, textAlign: 'center' }}>Ht (ft)</Muted>
              <Muted style={{ width: 72, fontWeight: '700', fontSize: 11, textAlign: 'center' }}>Status</Muted>
            </View>
            {shown.map((it, idx) => (
              <View key={it.LINE_ID ?? idx} style={{ flexDirection: 'row', paddingVertical: 5, borderBottomWidth: idx < shown.length - 1 ? 1 : 0, borderBottomColor: colors.border }}>
                <View style={{ flex: 2 }}>
                  <Muted style={{ fontWeight: '600', color: colors.text, fontSize: 12 }}>{CD_KIND[it.KIND] ?? 'Equipment'}{it.MODEL_TEXT ? ` — ${it.MODEL_TEXT}` : ''}</Muted>
                  {it.AZIMUTH_DEG != null ? <Muted style={{ fontSize: 11 }}>{`Az ${it.AZIMUTH_DEG}°`}</Muted> : null}
                </View>
                <Muted style={{ width: 56, textAlign: 'center', fontSize: 12 }}>{it.SECTOR ? `${it.SECTOR}${it.POSITION != null ? `-P${it.POSITION}` : ''}` : '—'}</Muted>
                <Muted style={{ width: 52, textAlign: 'center', fontSize: 12 }}>{it.RAD_CENTER_FT != null ? it.RAD_CENTER_FT : '—'}</Muted>
                <View style={{ width: 72, alignItems: 'center' }}>
                  <Badge text={CD_STATUS[it.STATUS] ?? it.STATUS ?? '—'} color={it.STATUS === 'New' ? colors.ok : it.STATUS === 'Remove' ? colors.danger : colors.muted} />
                </View>
              </View>
            ))}
            {main.length > CD_PREVIEW_ROWS ? (
              <Pressable onPress={() => setExpanded((v) => !v)} accessibilityRole="button" style={{ marginTop: space(1), paddingVertical: 6 }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: colors.primary }}>
                  {expanded ? 'Show less' : `+ ${main.length - CD_PREVIEW_ROWS} more antennas and radios — tap to show`}
                </Text>
              </Pressable>
            ) : null}
            {cd.trunk?.SPECIFIED_FT ? <Muted style={{ fontSize: 12, marginTop: space(1) }}>{`Cable run on the drawings: ${cd.trunk.SPECIFIED_FT} ft`}</Muted> : null}
          </>
        ) : isRunning ? (
          <Muted style={{ fontSize: 12 }}>Reading equipment from the drawings...</Muted>
        ) : (
          <Muted style={{ fontSize: 12 }}>No equipment was read. Check that a construction drawing is available for this site.</Muted>
        )}
      </View>
    </Card>
  );
}

function Extracted({ x, isRunning }: { x: any; isRunning?: boolean }) {
  const drone = x.drone_extraction || {
    formats: [],
    detected_formats: [],
    identified_objects: [],
    obj_type_counts: {},
    items_count: x.config_lines?.filter((c: R) => c.SOURCE === 'FIELD').length ?? 0,
    objects_count: 0,
    items: x.config_lines?.filter((c: R) => c.SOURCE === 'FIELD') ?? [],
    method: 'POINTCLOUD (LiDAR 3D)',
  };

  const cd = x.cd_extraction || {
    formats: [],
    detected_formats: [],
    revision: 'REV 1',
    method: 'DXF',
    items_count: x.config_lines?.filter((c: R) => c.SOURCE === 'CD').length ?? 0,
    items: x.config_lines?.filter((c: R) => c.SOURCE === 'CD') ?? [],
  };

  return (
    <View>
      <Row style={{ marginBottom: space(2) }}>
        <Stat label="Total Extracted Facts" value={x.total} />
        <Stat label="Drone Objects" value={drone.objects_count} color={colors.info} />
        <Stat label="CD Drawn Items" value={cd.items_count} color={colors.primary} />
        <Stat label="Need Review" value={x.needs_review} color={x.needs_review ? colors.warn : undefined} />
      </Row>

      {/* Stage 2 Parallel Cards: 1st Card Drone Data, 2nd Card CD Drawings Data */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(3), marginVertical: space(2) }}>
        {/* Card 1: Extraction of Drone Data — shows format check and identified objects only */}
        <DroneDataCard drone={drone} isRunning={isRunning} />

        {/* Card 2: Extraction of CD Drawing Data (same layout as the drone card) */}
        <CdDataCard cd={cd} isRunning={isRunning} />
      </View>

      {/* Low-confidence / reviewable values section (only when something needs review) */}
      {x.fields && x.fields.length > 0 && x.needs_review ? (
        <Section title={`Fields Requiring Review (${x.needs_review})`}>
          {x.fields.slice(0, 15).map((f: R) => (
            <Row key={f.FIELD_ID} style={{ justifyContent: 'space-between', paddingVertical: 4, borderBottomWidth: 1, borderBottomColor: colors.border }}>
              <View style={{ flex: 1 }}>
                <Muted style={{ color: colors.text, fontWeight: '600' }}>{`${f.FIELD_NAME} = ${show(f.VALUE)}`}</Muted>
                <Muted style={{ fontSize: 12 }}>{`${f.METHOD ?? 'Extracted'}${f.PAGE ? ` • Page ${f.PAGE}` : ''}`}</Muted>
              </View>
              <Badge text={`${Math.round((f.CONFIDENCE ?? 0) * 100)}%`} color={f.NEEDS_REVIEW ? colors.warn : colors.ok} />
            </Row>
          ))}
          {x.total > 15 ? <Muted style={{ marginTop: space(1) }}>{`...and ${x.total - 15} additional parameters extracted`}</Muted> : null}
        </Section>
      ) : null}
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
