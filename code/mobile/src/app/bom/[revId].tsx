// BOM revision: lines by sector with rule traceability, changes vs REV 0 with reason codes, scoper edits
// (DRAFT only, reason-coded, audited), review / handshake / FBA actions, and the Excel export.
import { Stack, useLocalSearchParams } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Linking, Modal, RefreshControl, ScrollView, TextInput, View } from 'react-native';
import { colors, space } from '../../components/theme';
import { Badge, Button, Card, Chips, Empty, ErrorView, KV, Loading, Muted, Row, s, Section, Title } from '../../components/ui';
import { ReasonPicker, WorkflowActions } from '../../components/WorkflowActions';
import { api, ApiError, authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { num, SECTOR, when } from '../../lib/format';
import { Row as R, WorkflowAction } from '../../lib/types';
import { useApi } from '../../lib/useApi';

type Tab = 'lines' | 'changes' | 'history';
interface Edit { mode: 'edit' | 'add' | 'delete'; line?: R }

function EditModal({ edit, revId, onClose, onSaved }: { edit: Edit; revId: string; onClose: () => void; onSaved: () => void }) {
  const l = edit.line;
  const [design, setDesign] = useState(String(l?.DESIGN_QTY ?? '1'));
  const [spare, setSpare] = useState(String(l?.SPARE_QTY ?? '0'));
  const [key, setKey] = useState('');
  const [sector, setSector] = useState('SITE');
  const [reason, setReason] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [err, setErr] = useState<ApiError | null>(null);
  const catalog = useApi<R[]>(edit.mode === 'add' ? '/reference/material_catalog' : null);
  const matches = (catalog.data ?? []).filter((c) => key.length > 1 && `${c.CATALOG_KEY} ${c.MODEL} ${c.DESCRIPTION}`.toLowerCase().includes(key.toLowerCase())).slice(0, 6);

  const save = async () => {
    setErr(null);
    try {
      if (edit.mode === 'edit') await api.patch(`/bom/lines/${l!.LINE_ID}`, { design_qty: Number(design), spare_qty: Number(spare), reason_code: reason, comment });
      else if (edit.mode === 'delete') await api.del(`/bom/lines/${l!.LINE_ID}?reason_code=${reason}&comment=${encodeURIComponent(comment)}`);
      else await api.post(`/bom/revisions/${revId}/lines`, { sector, catalog_key: key, design_qty: Number(design), spare_qty: Number(spare), reason_code: reason, comment });
      onSaved();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: '#0006', justifyContent: 'flex-end' }}>
        <ScrollView style={{ maxHeight: '90%', backgroundColor: colors.card, borderTopLeftRadius: 16, borderTopRightRadius: 16 }} contentContainerStyle={{ padding: space(4), gap: space(2) }}>
          <Title>{edit.mode === 'edit' ? `Edit ${l?.MODEL}` : edit.mode === 'delete' ? `Remove line ${l?.MODEL}` : 'Add a BOM line'}</Title>
          {edit.mode === 'add' ? (<>
            <TextInput style={s.input} placeholder="Search catalog (model, key or description)" value={key} onChangeText={setKey} />
            {matches.map((c) => <Card key={c.CATALOG_KEY} onPress={() => setKey(c.CATALOG_KEY)}><Title>{c.CATALOG_KEY}</Title><Muted>{`${c.MODEL} - ${c.DESCRIPTION}`}</Muted></Card>)}
            <Chips value={sector} onChange={setSector} options={['A', 'B', 'C', 'D', 'SITE'].map((k) => ({ key: k, label: SECTOR[k] }))} />
          </>) : null}
          {edit.mode !== 'delete' ? (
            <Row>
              <View style={{ flex: 1 }}><Muted>Design qty</Muted><TextInput style={s.input} keyboardType="numeric" value={design} onChangeText={setDesign} /></View>
              <View style={{ flex: 1 }}><Muted>Spare qty</Muted><TextInput style={s.input} keyboardType="numeric" value={spare} onChangeText={setSpare} /></View>
            </Row>
          ) : null}
          <Muted>Reason code (required)</Muted>
          <ReasonPicker value={reason} onChange={setReason} appliesTo="BOM_LINE" />
          <TextInput style={[s.input, { minHeight: 50 }]} multiline placeholder="Comment" value={comment} onChangeText={setComment} />
          {err ? <ErrorView error={err} /> : null}
          <Row><Button title="Cancel" kind="secondary" onPress={onClose} /><Button title="Save" kind={edit.mode === 'delete' ? 'danger' : 'primary'} disabled={!reason || (edit.mode === 'add' && !key)} onPress={save} /></Row>
        </ScrollView>
      </View>
    </Modal>
  );
}

export default function BomRevision() {
  const { revId } = useLocalSearchParams<{ revId: string }>();
  const rev = useApi<R & { ACTIONS: WorkflowAction[]; EDITABLE: boolean; HISTORY: R[] }>(`/bom/revisions/${revId}`);
  const lines = useApi<R[]>(`/bom/revisions/${revId}/lines`);
  const changes = useApi<R[]>(`/bom/revisions/${revId}/changes`);
  const { can } = useAuth();
  const [tab, setTab] = useState<Tab>('lines');
  const [edit, setEdit] = useState<Edit | null>(null);
  const reloadAll = () => { void rev.reload(); void lines.reload(); void changes.reload(); };
  const bySector = useMemo(() => {
    const m = new Map<string, R[]>();
    (lines.data ?? []).forEach((l) => m.set(l.SECTOR, [...(m.get(l.SECTOR) ?? []), l]));
    return [...m.entries()];
  }, [lines.data]);

  if (rev.error) return <View style={s.content}><ErrorView error={rev.error} onRetry={rev.reload} /></View>;
  if (!rev.data) return <Loading />;
  const r = rev.data;
  const canEdit = r.EDITABLE && can('SCOPER', 'REVIEWER');
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={lines.loading} onRefresh={reloadAll} />}>
      <Stack.Screen options={{ title: `${r.SITE_ID} ${r.REV_LABEL}` }} />
      <Card>
        <Row style={{ justifyContent: 'space-between' }}><Title>{`${r.SITE_ID} ${r.REV_LABEL}`}</Title><Row><Badge text={r.STATUS} />{r.LOCKED ? <Badge text="locked" color={colors.muted} /> : null}</Row></Row>
        <Muted>{r.KIND === 'TOOL_REV0' ? 'Ericsson tool export as received - read only' : `Generated ${when(r.CREATED_AT)}${r.APPROVED_BY ? ` - approved by ${r.APPROVED_BY}` : ''}`}</Muted>
        {r.TRUNK_PLAN ? <Muted>{`Trunk: ${r.TRUNK_PLAN.held ? 'HELD - route not documented' : `${r.TRUNK_PLAN.count} x ${r.TRUNK_PLAN.key} (${r.TRUNK_PLAN.length_ft} ft; required ${num(r.TRUNK_PLAN.required_ft)} ft, horizontal from ${r.TRUNK_PLAN.horizontal_basis})`}`}</Muted> : null}
        <View style={{ marginTop: space(2) }}><WorkflowActions actions={r.ACTIONS} endpoint={`/bom/revisions/${revId}/transition`} entity="BOM_REVISION" onDone={reloadAll} /></View>
        <Row style={{ marginTop: space(2) }}>
          <Button small kind="secondary" title="Export Excel" onPress={() => Linking.openURL(authedUrl(`/bom/revisions/${revId}/export`))} />
          {canEdit ? <Button small title="Add line" onPress={() => setEdit({ mode: 'add' })} /> : null}
        </Row>
      </Card>
      <Chips<Tab> value={tab} onChange={setTab} options={[{ key: 'lines', label: `Lines (${lines.data?.length ?? 0})` }, { key: 'changes', label: `Changes vs REV 0 (${changes.data?.length ?? 0})` }, { key: 'history', label: 'History' }]} />
      {tab === 'lines' && (lines.error ? <ErrorView error={lines.error} /> : !lines.data ? <Loading /> : bySector.map(([sec, ls]) => (
        <Section key={sec} title={`${SECTOR[sec] ?? sec} (${ls.length})`}>
          {ls.map((l) => (
            <Card key={l.LINE_ID} onPress={canEdit ? () => setEdit({ mode: 'edit', line: l }) : undefined}>
              <Row style={{ justifyContent: 'space-between' }}>
                <View style={{ flex: 1 }}><Title>{l.MODEL}</Title><Muted numberOfLines={1}>{`${l.DESCRIPTION} - ${l.MFR_PN}`}</Muted></View>
                <View style={{ alignItems: 'flex-end' }}><Title>{`${num(l.TOTAL_QTY)} ${l.UOM}`}</Title><Badge text={l.ACTION} /></View>
              </Row>
              <Row style={{ marginTop: 4 }}>
                {l.RULE_ID ? <Badge text={l.RULE_ID} color={colors.muted} /> : null}
                {l.REASON_CODE ? <Badge text={l.REASON_CODE} color={colors.warn} /> : null}
                {!l.APPROVED_PART ? <Badge text="not approved part" color={colors.danger} /> : null}
                {l.SPARE_QTY ? <Muted>{`incl. ${num(l.SPARE_QTY)} spare`}</Muted> : null}
                {l.EDITED_BY ? <Muted>{`edited by ${l.EDITED_BY}`}</Muted> : null}
              </Row>
              <Muted numberOfLines={2}>{l.SOURCE}</Muted>
              {canEdit ? <Row style={{ marginTop: 4 }}><Button small kind="secondary" title="Remove" onPress={() => setEdit({ mode: 'delete', line: l })} /></Row> : null}
            </Card>
          ))}
        </Section>
      )))}
      {tab === 'changes' && (!changes.data?.length ? <Empty text="No changes against REV 0." /> : changes.data.map((c) => (
        <Card key={c.CHANGE_ID}>
          <Row style={{ justifyContent: 'space-between' }}><Title>{`${SECTOR[c.SECTOR] ?? c.SECTOR}: ${c.CATALOG_KEY}`}</Title><Badge text={c.ACTION} /></Row>
          <Muted>{`REV 0 ${num(c.FROM_QTY)} -> ${num(c.TO_QTY)} (${c.DELTA > 0 ? '+' : ''}${num(c.DELTA)})`}</Muted>
          {(c.REASONS ?? []).map((x: R, i: number) => <KV key={i} k={x.reason_code} v={`${x.qty > 0 ? '+' : ''}${x.qty}  ${(x.disc_ids ?? []).join(', ')}`} />)}
        </Card>
      )))}
      {tab === 'history' && <Card>{r.HISTORY.length ? r.HISTORY.map((h) => <KV key={h.EVENT_ID} k={when(h.EVENT_TS)} v={`${h.FROM_STATE} -> ${h.TO_STATE} by ${h.ACTOR_USER_ID}${h.COMMENT ? `: ${h.COMMENT}` : ''}`} />) : <Muted>No transitions yet</Muted>}</Card>}
      {edit ? <EditModal edit={edit} revId={revId} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reloadAll(); }} /> : null}
    </ScrollView>
  );
}
