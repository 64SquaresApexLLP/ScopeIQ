import React, { useMemo, useState } from 'react';
import { Linking, Modal, Pressable, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { api, authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { money, SECTOR } from '../../lib/format';
import { HandshakeSummary } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { FilePreviewModal, FilePreviewTarget } from '../FilePreviewModal';
import { colors, space, statusColor } from '../theme';
import { Badge, Button, Card, Empty, ErrorView, Icon, IconBadge, Loading, Muted, Row, s, Title } from '../ui';
import { WorkflowActions } from '../WorkflowActions';

type SectionTab = 'review' | 'cd' | 'bom' | 'delta';

export function Handshake({ siteId }: { siteId: string }) {
  const { user } = useAuth();
  const { data, loading, error, reload } = useApi<HandshakeSummary>(`/sites/${siteId}/handshake`);
  const spsApi = useApi<{ user_id: string; name: string; market: string }[]>('/sites/service-providers');

  const [activeSection, setActiveSection] = useState<SectionTab>('review');
  const [previewTarget, setPreviewTarget] = useState<FilePreviewTarget | null>(null);
  const [bomFilter, setBomFilter] = useState<'ALL' | 'Install' | 'Remove'>('ALL');
  const [bomSearch, setBomSearch] = useState('');
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assigningSp, setAssigningSp] = useState(false);
  const [advancingWf, setAdvancingWf] = useState(false);

  const isSp = user?.role === 'CX_SP';
  const isAdmin = user?.role === 'ADMIN';

  const handleAssignSp = async (spName: string) => {
    setAssigningSp(true);
    try {
      await api.post(`/sites/${siteId}/assign-sp`, { cx_sp: spName });
      setShowAssignModal(false);
      reload();
    } catch (e: any) {
      alert(e?.message || 'Could not assign Service Provider');
    } finally {
      setAssigningSp(false);
    }
  };

  const handleAdvanceWorkflow = async (action: string) => {
    setAdvancingWf(true);
    try {
      await api.post(`/workflow/SITE_SCOPING/${siteId}/transition`, { action });
      reload();
    } catch (e: any) {
      alert(e?.message || `Could not advance workflow (${action})`);
    } finally {
      setAdvancingWf(false);
    }
  };

  const deltas = useMemo(() => data?.delta || [], [data?.delta]);
  const sectors = useMemo(() => [...new Set(deltas.map((d: any) => d.SECTOR || 'SITE'))], [deltas]);

  const newCount = useMemo(() => deltas.filter((d: any) => d.ACTION === 'NEW' || d.ACTION === 'INSTALL').length, [deltas]);
  const removeCount = useMemo(() => deltas.filter((d: any) => d.ACTION === 'REMOVED' || d.ACTION === 'REMOVE').length, [deltas]);
  const existingCount = useMemo(() => deltas.filter((d: any) => d.ACTION === 'EXISTING').length, [deltas]);
  const relocateCount = useMemo(() => deltas.filter((d: any) => d.ACTION === 'RELOCATED' || d.ACTION === 'REUSED').length, [deltas]);

  const bomLines = useMemo(() => data?.bom_lines || [], [data?.bom_lines]);
  const filteredBomLines = useMemo(() => {
    let list = bomLines;
    if (bomFilter !== 'ALL') {
      list = list.filter((b: any) => b.ACTION === bomFilter);
    }
    if (bomSearch.trim()) {
      const q = bomSearch.toLowerCase();
      list = list.filter(
        (b: any) =>
          (b.CATEGORY && b.CATEGORY.toLowerCase().includes(q)) ||
          (b.MODEL && b.MODEL.toLowerCase().includes(q)) ||
          (b.DESCRIPTION && b.DESCRIPTION.toLowerCase().includes(q)) ||
          (b.SECTOR && b.SECTOR.toLowerCase().includes(q))
      );
    }
    return list;
  }, [bomLines, bomFilter, bomSearch]);

  const cdDocs = useMemo(() => data?.cd_documents || [], [data?.cd_documents]);

  if (loading) return <Loading />;
  if (error) return <ErrorView error={error} onRetry={reload} />;
  if (!data) return <Empty text="No handshake data available for this site." />;

  const getActionColor = (action: string) => {
    switch (action) {
      case 'NEW':
      case 'INSTALL':
      case 'Install':
        return colors.ok;
      case 'REMOVED':
      case 'REMOVE':
      case 'Remove':
        return colors.danger;
      case 'RELOCATED':
      case 'REUSED':
        return colors.info;
      default:
        return colors.muted;
    }
  };

  const downloadBomUrl = authedUrl(
    `/sites/${siteId}/files/download?folder=bom&file_name=${encodeURIComponent(data.bom_summary.file_name)}`
  );

  return (
    <View style={{ gap: space(4) }}>
      {/* 1. Handshake Status & Top Decision Bar */}
      <Card style={{ gap: space(3) }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3) }}>
            <IconBadge
              name={data.is_fba_locked ? 'lock' : data.workflow_state === 'SUBMITTED_FBA' ? 'clock' : 'check-circle'}
              size={38}
              color={data.is_fba_locked ? colors.ok : data.workflow_state === 'SUBMITTED_FBA' ? colors.info : colors.accent}
            />
            <View>
              <Title>Site Build BOM Scoping (6.2)</Title>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
                <Text style={{ fontSize: 13, color: colors.muted }}>
                  Construction Provider: <Text style={{ fontWeight: '700', color: colors.text }}>{data.cx_sp || 'Not Assigned'}</Text>
                  {data.market ? ` · Market: ${data.market}` : ''}
                </Text>
                {(isAdmin || user?.role === 'SCOPER' || user?.role === 'REVIEWER') ? (
                  <Pressable
                    onPress={() => setShowAssignModal(true)}
                    style={{
                      paddingHorizontal: 8,
                      paddingVertical: 2,
                      borderRadius: 6,
                      backgroundColor: colors.accent + '18',
                      borderWidth: 1,
                      borderColor: colors.accent + '55',
                    }}
                  >
                    <Text style={{ fontSize: 11.5, fontWeight: '700', color: colors.accent }}>
                      {data.cx_sp ? 'Change SP' : '+ Assign SP'}
                    </Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
          </View>

          <Row>
            <Badge text={`State: ${data.workflow_state.replace(/_/g, ' ')}`} color={statusColor(data.workflow_state)} />
            <Badge
              text={data.has_bom && data.current_bom_rev && data.current_bom_rev !== '-' ? `BOM: ${data.current_bom_rev}` : 'No BOM'}
              color={data.has_bom ? (data.is_fba_locked ? colors.ok : colors.accent) : colors.muted}
            />
            {data.is_fba_locked ? <Badge text="FBA LOCKED" color={colors.ok} /> : null}
          </Row>
        </View>

        <Text style={{ fontSize: 13.5, color: colors.text, lineHeight: 20 }}>
          {data.is_fba_locked ? (
            '🔒 Final BOM Approved (FBA). The bill of materials and scope of work are locked and approved for construction.'
          ) : data.workflow_state === 'SUBMITTED_FBA' ? (
            '✓ Service Provider agreed to the Scope of Work and BOM. Ready for Final BOM Approval (FBA) by review lead.'
          ) : data.workflow_state === 'SP_HANDSHAKE' ? (
            data.has_bom && bomLines.length > 0 ? (
              isSp ? (
                'Review the CD Drawings, Equipment Delta (Scope of Work), and BOM below. When satisfied, click "SP AGREE" or "SP REQUEST CHANGES".'
              ) : (
                `Site is in SP Handshake with ${data.cx_sp || 'the Service Provider'}. Waiting for provider to review drawings and BOM to provide their agreement or change request.`
              )
            ) : (
              'Site is in SP Handshake, but no Bill of Materials (BOM) has been generated yet.'
            )
          ) : (
            `Workflow state: ${data.workflow_state.replace(/_/g, ' ')}. Handshake actions activate when site enters SP Handshake.`
          )}
        </Text>

        {/* Workflow Progression Banner: Advance Scoping package towards Handshake */}
        {data.has_bom && bomLines.length > 0 && data.workflow_state !== 'SP_HANDSHAKE' && data.workflow_state !== 'SUBMITTED_FBA' && !data.is_fba_locked && (isAdmin || user?.role === 'SCOPER' || user?.role === 'REVIEWER') ? (
          <View
            style={{
              marginTop: space(2),
              padding: space(3.5),
              backgroundColor: '#eff6ff',
              borderRadius: 10,
              borderWidth: 1,
              borderColor: '#bfdbfe',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: space(2.5),
            }}
          >
            <View style={{ flex: 1, minWidth: 260 }}>
              <Text style={{ fontSize: 13.5, fontWeight: '700', color: '#1e40af' }}>
                {data.workflow_state === 'IN_RECONCILIATION'
                  ? 'BOM & Scope Generated — Ready to Enter Scoping'
                  : data.workflow_state === 'IN_SCOPING'
                  ? 'BOM Scoping Complete — Ready for QA Review'
                  : data.workflow_state === 'IN_REVIEW'
                  ? `QA Review Approved — Ready to Submit to ${data.cx_sp || 'Service Provider'}`
                  : `Site in ${data.workflow_state.replace(/_/g, ' ')}`}
              </Text>
              <Text style={{ fontSize: 12, color: '#3b82f6', marginTop: 2, lineHeight: 17 }}>
                {data.workflow_state === 'IN_RECONCILIATION'
                  ? 'The pipeline has generated 66 BOM lines and reconciled drawing data. Advance to scoping to begin review.'
                  : data.workflow_state === 'IN_SCOPING'
                  ? 'The scoping package is ready. Submit for QA Lead review before sending to the Construction Service Provider.'
                  : data.workflow_state === 'IN_REVIEW'
                  ? `Submit the approved package to ${data.cx_sp || 'the Construction Service Provider'} for official Handshake review & agreement.`
                  : 'Advance the scoping workflow to proceed to the next stage.'}
              </Text>
            </View>

            {data.workflow_state === 'IN_RECONCILIATION' ? (
              <Button
                title={advancingWf ? 'Advancing...' : 'Advance to Scoping'}
                disabled={advancingWf}
                onPress={() => handleAdvanceWorkflow('GENERATE')}
              />
            ) : data.workflow_state === 'IN_SCOPING' ? (
              <Button
                title={advancingWf ? 'Submitting...' : 'Submit for QA Review'}
                disabled={advancingWf}
                onPress={() => handleAdvanceWorkflow('SUBMIT_REVIEW')}
              />
            ) : data.workflow_state === 'IN_REVIEW' ? (
              <Button
                title={advancingWf ? 'Submitting...' : 'Submit to SP Handshake'}
                disabled={advancingWf}
                onPress={() => handleAdvanceWorkflow('SUBMIT_TO_SP')}
              />
            ) : null}
          </View>
        ) : null}

        {/* Handshake Gate Banner: If BOM is missing */}
        {!data.has_bom || bomLines.length === 0 ? (
          <View
            style={{
              marginTop: space(2),
              padding: space(3.5),
              backgroundColor: '#fffbeb',
              borderRadius: 10,
              borderWidth: 1,
              borderColor: '#fde68a',
              flexDirection: 'row',
              alignItems: 'center',
              gap: space(3),
            }}
          >
            <View
              style={{
                width: 36,
                height: 36,
                borderRadius: 18,
                backgroundColor: '#fef3c7',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Icon name="alert-triangle" size={18} color="#b45309" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 13.5, fontWeight: '700', color: '#92400e' }}>
                Handshake Inactive — Bill of Materials (BOM) Required
              </Text>
              <Text style={{ fontSize: 12.5, color: '#b45309', marginTop: 2, lineHeight: 18 }}>
                The Handshake tab is locked because no Bill of Materials (BOM) or Construction Drawings have been processed for this site. Ingest site documents and run the pipeline to enable the Handshake review.
              </Text>
            </View>
          </View>
        ) : data.actions && data.actions.length > 0 && (data.workflow_state === 'SP_HANDSHAKE' || data.workflow_state === 'SUBMITTED_FBA') ? (
          <View style={{ marginTop: space(1), paddingTop: space(3), borderTopWidth: 1, borderTopColor: colors.border }}>
            <WorkflowActions
              actions={data.actions}
              endpoint={`/workflow/SITE_SCOPING/${siteId}/transition`}
              entity="SITE_SCOPING"
              onDone={reload}
            />
          </View>
        ) : null}
      </Card>

      {/* 2. Quick Navigation Tabs to Inspect CD / BOM / Delta */}
      <View style={{ flexDirection: 'row', gap: space(2), flexWrap: 'wrap' }}>
        {[
          { key: 'review', label: 'Overview & Summary', icon: 'grid' as const },
          { key: 'cd', label: `CD Drawings (${cdDocs.length})`, icon: 'file-text' as const },
          { key: 'bom', label: `BOM Lines (${bomLines.length})`, icon: 'table' as const },
          { key: 'delta', label: `Scope of Work (${deltas.length})`, icon: 'layers' as const },
        ].map((t) => {
          const active = activeSection === t.key;
          return (
            <Pressable
              key={t.key}
              onPress={() => setActiveSection(t.key as SectionTab)}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              style={({ pressed }: any) => ({
                flexDirection: 'row',
                alignItems: 'center',
                gap: space(1.5),
                paddingHorizontal: space(3),
                paddingVertical: space(2),
                borderRadius: 8,
                backgroundColor: active ? colors.accent : '#fff',
                borderWidth: 1,
                borderColor: active ? colors.accent : colors.border,
                opacity: pressed ? 0.8 : 1,
              })}
            >
              <Icon name={t.icon} size={15} color={active ? '#fff' : colors.muted} />
              <Text style={{ fontSize: 13, fontWeight: active ? '700' : '600', color: active ? '#fff' : colors.text }}>
                {t.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {/* SECTION: CD DRAWINGS */}
      {(activeSection === 'review' || activeSection === 'cd') && (
        <Card style={{ gap: space(3) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2.5) }}>
              <IconBadge name="file-text" size={32} color={colors.accent} />
              <View>
                <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>Construction Drawings (CD)</Text>
                <Text style={{ fontSize: 12, color: colors.muted }}>
                  Click "View Drawing" to inspect elevation, sector layout, and antenna mounts
                </Text>
              </View>
            </View>

            <Badge text={`${cdDocs.length} Drawing(s)`} color={colors.accent} />
          </View>

          {cdDocs.length === 0 ? (
            <Empty text="No Construction Drawings (CD) registered for this site." />
          ) : (
            <View style={{ gap: space(2) }}>
              {cdDocs.map((doc: any) => {
                const isCurrent = doc.STATUS === 'CURRENT';
                return (
                  <View
                    key={doc.DOC_ID || doc.FILE_NAME}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      backgroundColor: colors.bg,
                      padding: space(2.5),
                      borderRadius: 8,
                      borderWidth: 1,
                      borderColor: isCurrent ? colors.accent + '44' : colors.border,
                      flexWrap: 'wrap',
                      gap: space(2),
                    }}
                  >
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2.5), flex: 1, minWidth: 220 }}>
                      <Icon name="file" size={24} color={isCurrent ? colors.accent : colors.muted} />
                      <View>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(1.5) }}>
                          <Text style={{ fontSize: 13.5, fontWeight: '700', color: colors.text }}>{doc.FILE_NAME}</Text>
                          <Badge
                            text={doc.REVISION || (isCurrent ? 'CURRENT' : doc.STATUS)}
                            color={isCurrent ? colors.ok : colors.muted}
                          />
                        </View>
                        <Text style={{ fontSize: 11.5, color: colors.muted, marginTop: 2 }}>
                          {doc.SIZE_BYTES ? `${Math.round(doc.SIZE_BYTES / 1024)} KB` : ''} · {doc.STATUS}
                        </Text>
                      </View>
                    </View>

                    <Row style={{ gap: space(1.5) }}>
                      <Button
                        small
                        title="👁 View Drawing"
                        onPress={() =>
                          setPreviewTarget({
                            name: doc.FILE_NAME,
                            folder: doc.DOC_TYPE === 'CD_REDLINE' ? 'redlines' : 'cds',
                            siteId: siteId,
                            docId: doc.DOC_ID,
                            size: doc.SIZE_BYTES,
                          })
                        }
                      />
                      <Button
                        small
                        kind="secondary"
                        title="⬇ Download"
                        onPress={() =>
                          Linking.openURL(
                            authedUrl(
                              `/sharepoint/sites/${siteId}/files/download?folder=cds&file_name=${encodeURIComponent(
                                doc.FILE_NAME
                              )}`
                            )
                          )
                        }
                      />
                    </Row>
                  </View>
                );
              })}
            </View>
          )}
        </Card>
      )}

      {/* SECTION: BILL OF MATERIALS (BOM) */}
      {(activeSection === 'review' || activeSection === 'bom') && (
        <Card style={{ gap: space(3) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2.5) }}>
              <IconBadge name="table" size={32} color={colors.accent} />
              <View>
                <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>
                  Bill of Materials ({data.current_bom_rev})
                </Text>
                <Text style={{ fontSize: 12, color: colors.muted }}>
                  {data.bom_summary.lines_count} lines · Total Material Cost: {money(data.bom_summary.total_material_cost)}
                </Text>
              </View>
            </View>

            <Button
              small
              kind="secondary"
              title="⬇ Export BOM (.xlsx)"
              onPress={() => Linking.openURL(downloadBomUrl)}
            />
          </View>

          {/* Search & Filter Toolbar for BOM */}
          <View style={{ flexDirection: 'row', gap: space(2), alignItems: 'center', flexWrap: 'wrap' }}>
            <TextInput
              style={[s.input, { flex: 1, minWidth: 200, minHeight: 36, paddingVertical: 4 }]}
              placeholder="Filter by model, category, or sector..."
              value={bomSearch}
              onChangeText={setBomSearch}
            />

            <Row style={{ gap: space(1) }}>
              {(['ALL', 'Install', 'Remove'] as const).map((mode) => (
                <Pressable
                  key={mode}
                  onPress={() => setBomFilter(mode)}
                  style={{
                    paddingHorizontal: space(2.5),
                    paddingVertical: space(1.5),
                    borderRadius: 6,
                    backgroundColor: bomFilter === mode ? colors.accent : colors.bg,
                    borderWidth: 1,
                    borderColor: bomFilter === mode ? colors.accent : colors.border,
                  }}
                >
                  <Text style={{ fontSize: 12, fontWeight: '600', color: bomFilter === mode ? '#fff' : colors.text }}>
                    {mode === 'ALL' ? 'All Items' : mode}
                  </Text>
                </Pressable>
              ))}
            </Row>
          </View>

          {/* Interactive BOM Table Preview */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={{ minWidth: 780 }}>
              {/* Header */}
              <View
                style={{
                  flexDirection: 'row',
                  paddingVertical: space(2),
                  backgroundColor: colors.bg,
                  borderRadius: 6,
                  paddingHorizontal: space(2),
                  borderBottomWidth: 1.5,
                  borderBottomColor: colors.border,
                }}
              >
                <Text style={{ width: 140, fontSize: 11, fontWeight: '700', color: colors.muted, textTransform: 'uppercase' }}>Category</Text>
                <Text style={{ flex: 1, minWidth: 220, fontSize: 11, fontWeight: '700', color: colors.muted, textTransform: 'uppercase' }}>Model / Description</Text>
                <Text style={{ width: 65, fontSize: 11, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', textAlign: 'center' }}>Sec</Text>
                <Text style={{ width: 60, fontSize: 11, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', textAlign: 'right' }}>Qty</Text>
                <Text style={{ width: 85, fontSize: 11, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', textAlign: 'center' }}>Action</Text>
                <Text style={{ width: 100, fontSize: 11, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', textAlign: 'right' }}>Cost</Text>
              </View>

              {/* Rows */}
              {filteredBomLines.slice(0, activeSection === 'bom' ? 100 : 8).map((b: any, idx: number) => (
                <View
                  key={b.LINE_ID || idx}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    paddingVertical: space(1.5),
                    paddingHorizontal: space(2),
                    borderBottomWidth: 1,
                    borderBottomColor: colors.border + '55',
                    backgroundColor: idx % 2 === 1 ? colors.bg + '40' : undefined,
                  }}
                >
                  <Text style={{ width: 140, fontSize: 12.5, fontWeight: '600', color: colors.text }} numberOfLines={1}>
                    {b.CATEGORY || 'General'}
                  </Text>
                  <View style={{ flex: 1, minWidth: 220, paddingRight: space(2) }}>
                    <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }} numberOfLines={1}>
                      {b.MODEL || b.DESCRIPTION || 'Item'}
                    </Text>
                    {b.DESCRIPTION && b.MODEL ? (
                      <Text style={{ fontSize: 11, color: colors.muted }} numberOfLines={1}>
                        {b.DESCRIPTION}
                      </Text>
                    ) : null}
                  </View>
                  <Text style={{ width: 65, fontSize: 12.5, color: colors.muted, textAlign: 'center' }}>{b.SECTOR || '-'}</Text>
                  <Text style={{ width: 60, fontSize: 13, fontWeight: '700', color: colors.text, textAlign: 'right' }}>
                    {b.TOTAL_QTY ?? b.DESIGN_QTY ?? 1}
                  </Text>
                  <View style={{ width: 85, alignItems: 'center' }}>
                    <Badge text={b.ACTION || 'Install'} color={getActionColor(b.ACTION || 'Install')} />
                  </View>
                  <Text style={{ width: 100, fontSize: 12.5, fontWeight: '600', color: colors.text, textAlign: 'right' }}>
                    {b.TOTAL_COST_USD ? money(b.TOTAL_COST_USD) : '-'}
                  </Text>
                </View>
              ))}

              {activeSection !== 'bom' && filteredBomLines.length > 8 && (
                <Pressable
                  onPress={() => setActiveSection('bom')}
                  style={{ padding: space(2), alignItems: 'center', backgroundColor: colors.bg }}
                >
                  <Text style={{ color: colors.accent, fontSize: 12.5, fontWeight: '700' }}>
                    + View all {filteredBomLines.length} BOM lines in detail →
                  </Text>
                </Pressable>
              )}
            </View>
          </ScrollView>
        </Card>
      )}

      {/* SECTION: SCOPE OF WORK (EQUIPMENT DELTA) */}
      {(activeSection === 'review' || activeSection === 'delta') && (
        <Card style={{ gap: space(3) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2.5) }}>
              <IconBadge name="layers" size={32} color={colors.accent2} />
              <View>
                <Text style={{ fontSize: 15, fontWeight: '700', color: colors.text }}>Scope of Work (Equipment Delta)</Text>
                <Text style={{ fontSize: 12, color: colors.muted }}>
                  Physical changes verified between CD drawing and field conditions
                </Text>
              </View>
            </View>

            <Row style={{ gap: space(1.5) }}>
              <Badge text={`${newCount} to install`} color={colors.ok} />
              <Badge text={`${removeCount} to remove`} color={colors.danger} />
              {relocateCount > 0 ? <Badge text={`${relocateCount} relocated`} color={colors.info} /> : null}
              <Badge text={`${existingCount} existing`} color={colors.muted} />
            </Row>
          </View>

          {deltas.length === 0 ? (
            <Empty text="No equipment delta recorded yet." />
          ) : (
            <View style={{ gap: space(3) }}>
              {sectors.map((sec: string) => {
                const secDeltas = deltas.filter((d: any) => (d.SECTOR || 'SITE') === sec);
                if (!secDeltas.length) return null;
                return (
                  <View key={sec} style={{ borderRadius: 8, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' }}>
                    <View style={{ backgroundColor: colors.bg, paddingHorizontal: space(3), paddingVertical: space(2), borderBottomWidth: 1, borderBottomColor: colors.border }}>
                      <Text style={{ fontWeight: '800', fontSize: 13, color: colors.text }}>
                        Sector {SECTOR[sec] ? `${SECTOR[sec]} (${sec})` : sec}
                      </Text>
                    </View>

                    <View style={{ padding: space(2.5), gap: space(2) }}>
                      {secDeltas.map((r: any, idx: number) => (
                        <View
                          key={r.SEQ ?? idx}
                          style={{
                            flexDirection: 'row',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            paddingVertical: space(1.5),
                            borderBottomWidth: idx < secDeltas.length - 1 ? 1 : 0,
                            borderBottomColor: colors.border + '55',
                            flexWrap: 'wrap',
                            gap: space(1),
                          }}
                        >
                          <View style={{ flex: 1, minWidth: 220 }}>
                            <Text style={{ fontSize: 13.5, fontWeight: '700', color: colors.text }}>
                              {r.POSITION ? `Position ${r.POSITION} · ` : ''}
                              {r.KIND ? `${r.KIND}: ` : ''}
                              {r.CATALOG_KEY || 'Equipment item'}
                              {r.RAD_CENTER_FT ? ` @ ${r.RAD_CENTER_FT} ft` : ''}
                            </Text>
                            <Text style={{ fontSize: 11.5, color: colors.muted, marginTop: 2 }}>
                              {r.BASIS || 'Final design'}
                              {r.SOURCE_REF ? ` — ${r.SOURCE_REF}` : ''}
                            </Text>
                          </View>

                          <Badge text={r.ACTION} color={getActionColor(r.ACTION)} />
                        </View>
                      ))}
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </Card>
      )}

      {/* 3. Bottom Decision Call-to-Action Bar */}
      {data.workflow_state === 'SP_HANDSHAKE' && isSp && (data.has_bom || bomLines.length > 0) && (
        <Card style={{ backgroundColor: colors.primary + '10', borderColor: colors.primary + '33', gap: space(2.5) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
            <View>
              <Text style={{ fontSize: 15, fontWeight: '800', color: colors.text }}>Completed reviewing CD & BOM?</Text>
              <Text style={{ fontSize: 12.5, color: colors.muted }}>
                Submit your official handshake decision below to proceed towards Final BOM Approval (FBA).
              </Text>
            </View>
          </View>

          <WorkflowActions
            actions={data.actions}
            endpoint={`/workflow/SITE_SCOPING/${siteId}/transition`}
            entity="SITE_SCOPING"
            onDone={reload}
          />
        </Card>
      )}

      {/* 4. Review History / Audit Trail */}
      <Card style={{ gap: space(2.5) }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2.5) }}>
          <IconBadge name="clock" size={28} color={colors.muted} />
          <View>
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>Handshake & Review History</Text>
            <Text style={{ fontSize: 11.5, color: colors.muted }}>Audit trail of sign-offs, change requests, and approvals</Text>
          </View>
        </View>

        {(!data.workflow_history || data.workflow_history.length === 0) ? (
          <View style={{ marginTop: space(1), borderTopWidth: 1, borderTopColor: colors.border, paddingTop: space(2) }}>
            <Text style={{ fontSize: 13, color: colors.muted, fontStyle: 'italic' }}>
              No handshake or review events recorded yet for this site.
            </Text>
          </View>
        ) : (
          <View style={{ marginTop: space(1), borderTopWidth: 1, borderTopColor: colors.border, paddingTop: space(2), gap: space(2) }}>
            {data.workflow_history.map((ev: any, idx: number) => (
              <View
                key={ev.EVENT_ID ?? idx}
                style={{
                  flexDirection: 'row',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  paddingVertical: space(1.5),
                  borderBottomWidth: idx < data.workflow_history.length - 1 ? 1 : 0,
                  borderBottomColor: colors.border + '44',
                  flexWrap: 'wrap',
                  gap: space(1),
                }}
              >
                <View style={{ flex: 1, minWidth: 220 }}>
                  <Row style={{ gap: space(1.5) }}>
                    <Text style={{ fontWeight: '700', fontSize: 13, color: colors.text }}>{ev.ACTION.replace(/_/g, ' ')}</Text>
                    <Badge text={`${ev.FROM_STATE} → ${ev.TO_STATE}`} color={statusColor(ev.TO_STATE)} />
                  </Row>
                  {ev.REASON_CODE ? (
                    <Text style={{ fontSize: 12, fontWeight: '600', color: colors.accent, marginTop: 2 }}>
                      Reason: {ev.REASON_CODE}
                    </Text>
                  ) : null}
                  {ev.COMMENT ? (
                    <Text style={{ fontSize: 12, color: colors.muted, marginTop: 2 }}>"{ev.COMMENT}"</Text>
                  ) : null}
                </View>

                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={{ fontSize: 11, color: colors.muted }}>By {ev.ACTOR || 'system'}</Text>
                  <Text style={{ fontSize: 10.5, color: colors.muted }}>
                    {ev.EVENT_TIME ? new Date(ev.EVENT_TIME).toLocaleString() : ''}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </Card>

      {/* Embedded File Preview Modal for CD Drawings */}
      <FilePreviewModal target={previewTarget} onClose={() => setPreviewTarget(null)} />

      {/* Assign SP Modal */}
      <Modal visible={showAssignModal} transparent animationType="fade" onRequestClose={() => setShowAssignModal(false)}>
        <TouchableOpacity
          activeOpacity={1}
          onPress={() => setShowAssignModal(false)}
          style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', alignItems: 'center', padding: space(4) }}
        >
          <TouchableOpacity
            activeOpacity={1}
            style={{ width: '100%', maxWidth: 480, backgroundColor: '#fff', borderRadius: 16, padding: space(5), gap: space(3) }}
          >
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <View>
                <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text }}>Assign Construction Provider (SP)</Text>
                <Text style={{ fontSize: 13, color: colors.muted, marginTop: 2 }}>
                  Select the Construction Service Provider hired to build this site.
                </Text>
              </View>
              <Pressable onPress={() => setShowAssignModal(false)}>
                <Icon name="x" size={20} color={colors.muted} />
              </Pressable>
            </View>

            <View style={{ gap: space(2), marginTop: space(2) }}>
              {(spsApi.data || [
                { user_id: 'sp_prairie', name: 'Prairie Tower Services (synthetic)', market: 'DFW' },
                { user_id: 'sp_brazos', name: 'Brazos Wireless Construction (synthetic)', market: 'DFW' },
                { user_id: 'sp_redline', name: 'Redline Constructors (synthetic)', market: 'DFW' },
              ]).map((sp) => {
                const isCurrent = data.cx_sp === sp.name;
                return (
                  <Pressable
                    key={sp.user_id}
                    disabled={assigningSp}
                    onPress={() => handleAssignSp(sp.name)}
                    style={({ pressed, hovered }: any) => [
                      {
                        flexDirection: 'row',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: space(3.5),
                        borderRadius: 12,
                        borderWidth: 1,
                        borderColor: isCurrent ? colors.accent : hovered ? colors.accent : colors.border,
                        backgroundColor: isCurrent ? colors.accent + '10' : '#fff',
                        opacity: pressed ? 0.8 : 1,
                      },
                    ]}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 14.5, fontWeight: '700', color: colors.text }}>{sp.name}</Text>
                      <Text style={{ fontSize: 12, color: colors.muted, marginTop: 2 }}>
                        Market: {sp.market || 'DFW'} · Account: {sp.user_id}
                      </Text>
                    </View>
                    {isCurrent ? (
                      <Badge text="ASSIGNED" color={colors.ok} />
                    ) : (
                      <Icon name="chevron-right" size={16} color={colors.muted} />
                    )}
                  </Pressable>
                );
              })}
            </View>

            <Button title="Close" kind="secondary" onPress={() => setShowAssignModal(false)} />
          </TouchableOpacity>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}
