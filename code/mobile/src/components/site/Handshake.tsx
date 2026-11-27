// Scope of work and BOM, in the order the work happens: where the package is, what happens now (and whose turn it is), then the package itself.
// Written for people who do not know the tool: plain words, one clear next step, and a confirmation that says what the step does.
import React, { useMemo, useState } from 'react';
import { Linking, Pressable, Text, TextInput, View } from 'react-native';
import { api, ApiError, authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { clean, money, roleLabel, SECTOR, when } from '../../lib/format';
import { BomChange, BomRevisionInfo, HandshakeSummary, Row as R, WorkflowAction } from '../../lib/types';
import { mutateApi, useApi } from '../../lib/useApi';
import { FilePreviewModal, FilePreviewTarget } from '../FilePreviewModal';
import { colors, radius, space } from '../theme';
import {
  Badge, Banner, Button, Card, Chips, Column, DataTable, Dialog, Empty, EmptyState, ErrorView, humanize, Icon, IconBadge, IconButton, Loading, Muted, Row, s,
  SearchBox, SegmentedTabs, Select, Stat,
} from '../ui';
import { useReasonCodes } from '../WorkflowActions';

type Tab = 'bom' | 'scope' | 'drawings' | 'history';

// where the package is, left to right
const STAGES: { label: string; states: string[] }[] = [
  { label: 'Scoping', states: ['ASSIGNED', 'DOCS_INGESTED', 'EXTRACTED', 'IN_RECONCILIATION', 'IN_SCOPING', 'REWORK'] },
  { label: 'Review', states: ['IN_REVIEW'] },
  { label: 'Service provider', states: ['SP_HANDSHAKE'] },
  { label: 'Final approval', states: ['SUBMITTED_FBA'] },
  { label: 'Approved', states: ['FBA_APPROVED'] },
];
const STATE_TITLE: Record<string, string> = {
  IN_SCOPING: 'With the scoping team', REWORK: 'Reopened for changes', IN_REVIEW: 'With the reviewer', SP_HANDSHAKE: 'With the service provider',
  SUBMITTED_FBA: 'Waiting for final approval', FBA_APPROVED: 'Approved and locked', ON_HOLD: 'On hold',
};
// what each step is called on its button, and what it does (shown before it is taken)
const STEP_COPY: Record<string, { label: string; what: (provider: string, rev: string) => string; kind?: 'primary' | 'secondary' | 'danger'; icon?: any }> = {
  SUBMIT_REVIEW: { label: 'Send for review', icon: 'send', what: (_p, rev) => `The reviewer will check the scope of work and ${rev} of the BOM.` },
  RETURN_TO_SCOPER: { label: 'Send back to the scoper', kind: 'secondary', icon: 'corner-up-left', what: () => 'The scoper gets the package back to correct it.' },
  SUBMIT_TO_SP: { label: 'Send to the service provider', icon: 'send', what: (p, rev) => `${p || 'The service provider'} will see the final drawings, the scope of work and ${rev} of the BOM. ${rev} is locked from now on: it cannot be changed, only replaced by a new revision.` },
  APPROVE_FBA: { label: 'Give final approval', icon: 'check-circle', what: (_p, rev) => `${rev} of the scope of work and BOM becomes final and is locked. It cannot be edited afterwards.` },
  REJECT_FBA: { label: 'Send back for changes', kind: 'secondary', icon: 'corner-up-left', what: () => 'The package goes back to the scoping team. Tell them what has to change.' },
  TRIGGER_REWORK: { label: 'Reopen for changes', kind: 'secondary', icon: 'rotate-ccw', what: (_p, rev) => `The package is reopened. ${rev} stays as it is; the scoping team prepares the next revision.` },
  HOLD: { label: 'Put on hold', kind: 'secondary', icon: 'pause-circle', what: () => 'Work on this site stops until it is released.' },
  RELEASE: { label: 'Release from hold', icon: 'play-circle', what: () => 'Work on this site continues.' },
  GENERATE: { label: 'Continue to scoping', icon: 'arrow-right-circle', what: () => 'The site goes back to the scoping team to prepare the next revision.' },
  AGREE: { label: 'Agree', icon: 'check', what: (p) => `Records that ${p || 'the service provider'} agrees to the scope of work and the BOM.` },
  REQUEST_CHANGES: { label: 'Ask for changes', kind: 'secondary', icon: 'edit-3', what: () => 'Asks the scoping team to change the package.' },
};
const HIDDEN_STEPS = ['INGEST', 'EXTRACT', 'RECONCILE', 'AGREE', 'REQUEST_CHANGES'];   // the pipeline takes the first three; the service provider answers for itself
const HISTORY_COPY: Record<string, string> = {
  SUBMIT_REVIEW: 'Sent for review', RETURN_TO_SCOPER: 'Sent back to the scoper', SUBMIT_TO_SP: 'Sent to the service provider', AGREE: 'Service provider agreed',
  REQUEST_CHANGES: 'Service provider asked for changes', SP_REQUEST_CHANGES: 'Service provider asked for changes', APPROVE_FBA: 'Final approval given',
  REJECT_FBA: 'Final approval refused and sent back', TRIGGER_REWORK: 'Reopened for changes', HOLD: 'Put on hold', RELEASE: 'Released from hold',
};
const REV_STATUS: Record<string, { text: string; color: string }> = {
  DRAFT: { text: 'Draft', color: colors.warn }, IN_REVIEW: { text: 'In review', color: colors.info }, APPROVED: { text: 'Approved', color: colors.ok },
  SP_REVIEW: { text: 'With service provider', color: colors.info }, SP_CHANGES_REQUESTED: { text: 'Changes requested', color: colors.danger },
  SP_AGREED: { text: 'Agreed by provider', color: colors.ok }, FBA: { text: 'Approved', color: colors.ok }, SUPERSEDED: { text: 'Replaced', color: colors.neutral },
};
const ACTION_TONE = (a?: string) => (/^install$/i.test(a ?? '') ? colors.ok : /^remove$/i.test(a ?? '') ? colors.danger : colors.muted);
const DELTA_TEXT: Record<string, string> = { NEW: 'Install new', INSTALL: 'Install new', REMOVED: 'Remove', REMOVE: 'Remove', EXISTING: 'Keep as it is', RELOCATED: 'Move', REUSED: 'Reuse' };
const act = (d: R) => String(d.ACTION ?? '').toUpperCase();
const DELTA_TONE: Record<string, string> = { NEW: colors.ok, INSTALL: colors.ok, REMOVED: colors.danger, REMOVE: colors.danger, RELOCATED: colors.info, REUSED: colors.info };

const PAGE = 20;
const asDate = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : '');

export function Handshake({ siteId }: { siteId: string }) {
  const { user } = useAuth();
  const [rev, setRev] = useState<string | null>(null);
  const { data, loading, error, reload } = useApi<HandshakeSummary>(`/sites/${siteId}/handshake${rev ? `?rev=${encodeURIComponent(rev)}` : ''}`);
  const [tab, setTab] = useState<Tab>('bom');
  const [preview, setPreview] = useState<FilePreviewTarget | null>(null);
  const [step, setStep] = useState<WorkflowAction | null>(null);
  const [provider, setProvider] = useState(false);
  const [edit, setEdit] = useState<{ mode: 'edit' | 'add' | 'remove'; line?: R } | null>(null);
  const [startError, setStartError] = useState<ApiError | null>(null);
  const reasons = useReasonCodes();
  const canAssign = user?.role === 'ADMIN' || user?.role === 'SCOPER' || user?.role === 'REVIEWER';

  const done = () => { setRev(null); reload(); mutateApi(); };       // the site header (its state) follows the step too
  const describe = (code?: string | null) => reasons.find((c) => c.REASON_CODE === code)?.DESCRIPTION || code || '';

  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorView error={error} onRetry={reload} />;
  if (!data) return <Empty text="Nothing to show for this site yet." />;

  const state = data.workflow_state;
  const bomLines = data.bom_lines ?? [];
  const revs = data.revisions ?? [];
  const shown = revs.find((x) => x.id === data.selected_rev) ?? null;
  const revLabel = shown?.label ?? data.current_bom_rev ?? 'REV 1';
  const providerName = clean(data.cx_sp);
  const steps = (data.workflow_actions ?? []).filter((a) => !HIDDEN_STEPS.includes(a.action) && (a.action !== 'GENERATE' || state === 'REWORK'));
  const mine = !!data.can_start_next_rev || steps.some((a) => !STEP_COPY[a.action]?.kind);       // a step that moves the package on is waiting for this user
  const stageIdx = STAGES.findIndex((g) => g.states.includes(state));
  const latest = revs[0];
  const asked = state === 'IN_SCOPING' || state === 'REWORK'
    ? (data.workflow_history ?? []).find((h) => /REQUEST_CHANGES/.test(h.ACTION)) : undefined;

  const startNext = async () => {
    setStartError(null);
    try { await api.post(`/bom/sites/${siteId}/next-revision`); done(); } catch (e) { setStartError(e as ApiError); }
  };

  return (
    <View style={{ gap: space(4) }}>
      {/* where the package is */}
      <Card style={{ gap: space(4) }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(3) }}>
          <View style={{ flex: 1, minWidth: 260, gap: 4 }}>
            <Text style={{ fontSize: 17, fontWeight: '700', color: colors.text }}>Scope of work and BOM</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
              <Text style={{ fontSize: 13.5, color: colors.muted }}>
                Service provider: <Text style={{ fontWeight: '700', color: providerName ? colors.text : colors.warn }}>{providerName || 'Not chosen yet'}</Text>
              </Text>
              {canAssign && !data.package_out ? (
                <Button small kind="ghost" icon="edit-2" title={providerName ? 'Change' : 'Choose'} onPress={() => setProvider(true)} />
              ) : null}
            </View>
          </View>
          <Row>
            {data.has_bom && revLabel !== '-' ? <Badge text={revLabel} color={data.is_fba_locked ? colors.ok : colors.accent} /> : null}
            {data.is_fba_locked ? <Badge text="Approved and locked" color={colors.ok} /> : null}
          </Row>
        </View>
        <Stages index={stageIdx} hold={state === 'ON_HOLD'} />
      </Card>

      {/* what happens now */}
      <Card style={{ gap: space(3), borderLeftWidth: 4, borderLeftColor: mine ? colors.accent : colors.borderStrong }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
          <Text style={{ fontSize: 15.5, fontWeight: '700', color: colors.text }}>{STATE_TITLE[state] ?? humanize(state)}</Text>
          {mine
            ? <Badge text="Needs your action" color={colors.warn} dot />
            : data.is_fba_locked ? <Badge text="Complete" color={colors.ok} dot />
              : <Badge text={data.owner_role ? `Waiting for ${roleLabel(data.owner_role)}` : 'Nothing to do'} color={colors.neutral} dot />}
        </View>
        {data.state_description && !same(data.state_description, STATE_TITLE[state]) ? <Text style={{ fontSize: 13.5, color: colors.muted, lineHeight: 20 }}>{data.state_description}</Text> : null}

        {asked ? (
          <Banner kind="warn" title={`${providerName || 'The service provider'} asked for changes`}>
            {[describe(asked.REASON_CODE), asked.COMMENT ? `“${asked.COMMENT}”` : ''].filter(Boolean).join(' · ')}
          </Banner>
        ) : null}
        {data.can_start_next_rev && latest ? (
          <Banner kind="info" title={`${latest.label} cannot be changed any more`}
            action={<Button small icon="plus" title={`Start ${nextLabel(latest.label)}`} onPress={startNext} />}>
            {`It was sent on. The next revision starts as a copy of ${latest.label}; every change you make needs a reason, and the differences are kept.`}
          </Banner>
        ) : null}
        {startError ? <ErrorView error={startError} /> : null}
        {!data.has_bom ? (
          <Banner kind="warn" title="No BOM yet">The BOM appears here once the site has been scoped.</Banner>
        ) : steps.length ? (
          <Row style={{ gap: space(2) }}>
            {steps.map((a) => {
              const c = STEP_COPY[a.action];
              const blocked = a.action === 'SUBMIT_TO_SP' && !providerName;
              return (
                <Button key={a.action} kind={c?.kind ?? 'primary'} icon={c?.icon} title={c?.label ?? humanize(a.action)} disabled={blocked} onPress={() => setStep(a)} />
              );
            })}
          </Row>
        ) : null}
        {steps.some((a) => a.action === 'SUBMIT_TO_SP') && !providerName ? (
          <Muted>Choose the service provider above before sending the BOM.</Muted>
        ) : null}
      </Card>

      {/* the package */}
      <View style={{ gap: space(3) }}>
        <SegmentedTabs value={tab} onChange={setTab} tabs={[
          { key: 'bom', label: 'BOM', icon: 'list', count: bomLines.length },
          { key: 'scope', label: 'Scope of work', icon: 'layers', count: data.delta?.length ?? 0 },
          { key: 'drawings', label: 'Drawings', icon: 'file-text', count: data.cd_documents?.length ?? 0 },
          { key: 'history', label: 'History', icon: 'clock', count: data.workflow_history?.length ?? 0 },
        ]} />

        {tab === 'bom' ? (
          <BomPanel data={data} siteId={siteId} revs={revs} shown={shown} onPick={(id) => setRev(id)} describe={describe}
            onEdit={(mode, line) => setEdit({ mode, line })} />
        ) : null}
        {tab === 'scope' ? <ScopePanel delta={data.delta ?? []} /> : null}
        {tab === 'drawings' ? <DrawingsPanel docs={data.cd_documents ?? []} siteId={siteId} onView={setPreview} /> : null}
        {tab === 'history' ? <HistoryPanel events={data.workflow_history ?? []} describe={describe} me={user?.user_id} /> : null}
      </View>

      <FilePreviewModal target={preview} onClose={() => setPreview(null)} />
      <StepDialog step={step} siteId={siteId} provider={providerName} rev={revLabel} onClose={() => setStep(null)} onDone={() => { setStep(null); done(); }} />
      <ProviderDialog open={provider} siteId={siteId} current={data.cx_sp} onClose={() => setProvider(false)} onDone={() => { setProvider(false); reload(); }} />
      {edit && shown ? <LineDialog edit={edit} rev={shown} onClose={() => setEdit(null)} onDone={() => { setEdit(null); reload(); }} /> : null}
    </View>
  );
}

const same = (a?: string, b?: string) => !!b && (a ?? '').trim().replace(/\.$/, '').toLowerCase().startsWith((b ?? '').trim().replace(/\.$/, '').toLowerCase());
const nextLabel = (label: string) => `REV ${(parseInt(label.replace(/\D/g, ''), 10) || 0) + 1}`;

// ------------------------------------------------------------------------------------------------ progress
function Stages({ index, hold }: { index: number; hold: boolean }) {
  return (
    <View>
      <View style={{ flexDirection: 'row' }}>
        {STAGES.map((g, i) => {
          const finished = !hold && index >= 0 && (i < index || (i === index && i === STAGES.length - 1));
          const current = !hold && i === index && !finished;
          const tone = finished ? colors.ok : current ? colors.accent : colors.faint;
          const line = (on: boolean, show: boolean) => <View style={{ flex: 1, height: 2, backgroundColor: show ? (on ? colors.ok : colors.border) : 'transparent' }} />;
          return (
            <View key={g.label} style={{ flex: 1, alignItems: 'center', gap: 6 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', alignSelf: 'stretch' }}>
                {line(finished || i <= index, i > 0)}
                <View style={{ width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: tone,
                  backgroundColor: finished ? colors.ok : current ? colors.accent : '#fff' }}>
                  {finished ? <Icon name="check" size={15} color="#fff" /> : <Text style={{ fontSize: 12.5, fontWeight: '700', color: current ? '#fff' : colors.faint }}>{i + 1}</Text>}
                </View>
                {line(finished, i < STAGES.length - 1)}
              </View>
              <Text style={{ fontSize: 12, fontWeight: current ? '700' : '500', color: current ? colors.text : colors.muted, textAlign: 'center', paddingHorizontal: 2 }}>{g.label}</Text>
            </View>
          );
        })}
      </View>
      {hold ? <Text style={{ marginTop: space(2), fontSize: 12.5, color: colors.warn, fontWeight: '600' }}>On hold. Work continues when it is released.</Text> : null}
    </View>
  );
}

// ------------------------------------------------------------------------------------------------ BOM
function BomPanel({ data, siteId, revs, shown, onPick, describe, onEdit }: {
  data: HandshakeSummary; siteId: string; revs: BomRevisionInfo[]; shown: BomRevisionInfo | null; onPick: (id: string) => void; describe: (c?: string | null) => string;
  onEdit: (mode: 'edit' | 'add' | 'remove', line?: R) => void;
}) {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<'ALL' | 'Install' | 'Remove'>('ALL');
  const [changes, setChanges] = useState(true);
  const [all, setAll] = useState(false);
  const lines = data.bom_lines ?? [];
  const editable = data.bom_editable;
  const count = (a: string) => lines.filter((l) => String(l.ACTION).toLowerCase() === a.toLowerCase()).length;
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return lines.filter((l) => (kind === 'ALL' || String(l.ACTION).toLowerCase() === kind.toLowerCase())
      && (!q || [l.MODEL, l.DESCRIPTION, l.CATEGORY, SECTOR[l.SECTOR] ?? l.SECTOR].some((v) => String(v ?? '').toLowerCase().includes(q))));
  }, [lines, query, kind]);
  const priced = lines.some((l) => l.TOTAL_COST_USD);
  const status = shown ? REV_STATUS[shown.status] ?? { text: humanize(shown.status), color: colors.neutral } : null;
  const approved = data.is_fba_locked && shown?.status === 'FBA';

  if (!lines.length) return <Card><EmptyState icon="list" title="No BOM yet" text="The BOM appears here once the site has been scoped." /></Card>;

  const columns: Column<R>[] = [
    { key: 'item', title: 'Item', flex: 2.4, render: (l) => (
      <View style={{ gap: 2 }}>
        <Text style={{ fontSize: 13.5, fontWeight: '700', color: colors.text }} numberOfLines={1}>{l.MODEL || l.DESCRIPTION || 'Item'}</Text>
        <Text style={{ fontSize: 12, color: colors.muted }} numberOfLines={1}>{[l.CATEGORY, l.MODEL ? l.DESCRIPTION : null].filter(Boolean).join(' · ')}</Text>
        {l.REASON_CODE ? <Text style={{ fontSize: 11.5, color: colors.accent }} numberOfLines={1}>{`Changed: ${describe(l.REASON_CODE)}`}</Text> : null}
      </View>
    ) },
    { key: 'sector', title: 'Sector', width: 90, render: (l) => <Text style={{ fontSize: 13, color: colors.muted }}>{SECTOR[l.SECTOR] ?? l.SECTOR ?? 'Site'}</Text> },
    { key: 'qty', title: 'Quantity', width: 90, align: 'right', render: (l) => <Text style={{ fontSize: 13.5, fontWeight: '700', color: colors.text }}>{l.TOTAL_QTY ?? l.DESIGN_QTY ?? 1}</Text> },
    { key: 'act', title: 'What to do', width: 120, render: (l) => <Badge text={String(l.ACTION).toLowerCase() === 'remove' ? 'Remove' : 'Install'} color={ACTION_TONE(l.ACTION)} /> },
    ...(priced ? [{ key: 'cost', title: 'Cost', width: 100, align: 'right' as const, render: (l: R) => <Text style={{ fontSize: 13, color: colors.text }}>{l.TOTAL_COST_USD ? money(l.TOTAL_COST_USD) : ''}</Text> }] : []),
    ...(editable ? [{ key: 'edit', title: '', width: 90, render: (l: R) => (
      <View style={{ flexDirection: 'row', gap: 2 }}>
        <IconButton icon="edit-2" label={`Change ${l.MODEL}`} onPress={() => onEdit('edit', l)} />
        <IconButton icon="trash-2" danger label={`Remove ${l.MODEL}`} onPress={() => onEdit('remove', l)} />
      </View>
    ) }] : []),
  ];

  return (
    <View style={{ gap: space(3) }}>
      {lines.length > 0 ? (
        <Card style={{ gap: space(3) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
            <View style={{ gap: 2 }}>
              <Text style={{ fontSize: 14.5, fontWeight: '700', color: colors.text }}>{revs.length ? 'Revisions' : 'Bill of materials'}</Text>
              <Muted>{revs.length ? 'Every BOM is kept. A revision that was sent to the service provider never changes.' : 'The BOM made for this site.'}</Muted>
            </View>
            <Button small kind={approved ? 'primary' : 'secondary'} icon="download" title={approved ? 'Download approved BOM (Excel)' : 'Download this BOM (Excel)'}
              onPress={() => Linking.openURL(authedUrl(`/bom/sites/${siteId}/export${shown ? `?rev=${encodeURIComponent(shown.id)}` : ''}`))} />
          </View>
          {revs.length ? <Chips value={shown?.id ?? revs[0].id} onChange={onPick} options={revs.map((x) => ({ key: x.id, label: x.label }))} /> : null}
          {shown ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
              {status ? <Badge text={status.text} color={status.color} dot /> : null}
              <Muted>
                {shown.locked ? <Icon name="lock" size={12} /> : null}
                {` ${shown.locked ? 'Locked. ' : 'Can still be changed. '}`}
                {shown.created_at ? `Made ${asDate(shown.created_at)}${shown.created_by ? ` by ${shown.created_by}` : ''}.` : ''}
                {shown.approved_at ? ` ${shown.status === 'FBA' ? 'Approved' : 'Locked'} ${asDate(shown.approved_at)}${shown.approved_by ? ` by ${shown.approved_by}` : ''}.` : ''}
              </Muted>
              {!shown.is_latest ? <Badge text="Earlier revision" color={colors.neutral} /> : null}
            </View>
          ) : null}
        </Card>
      ) : null}

      <View style={{ flexDirection: 'row', gap: space(3), flexWrap: 'wrap' }}>
        <Stat label="Items" value={lines.length} icon="list" />
        <Stat label="To install" value={count('Install')} icon="plus-circle" color={colors.ok} />
        <Stat label="To remove" value={count('Remove')} icon="minus-circle" color={count('Remove') ? colors.danger : undefined} />
        {data.bom_summary?.total_material_cost ? <Stat label="Material cost" value={money(data.bom_summary.total_material_cost)} icon="dollar-sign" /> : null}
      </View>

      {data.bom_changes?.length || (shown && shown.label !== 'REV 1' && revs.length > 1) ? (
        <Card style={{ gap: space(2) }}>
          <Pressable onPress={() => setChanges((v) => !v)} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={{ fontSize: 14.5, fontWeight: '700', color: colors.text }}>
              {`What changed since ${data.bom_changes?.[0]?.from_rev ?? 'the revision before'}`}
              <Text style={{ color: colors.muted, fontWeight: '500' }}>{`  ·  ${data.bom_changes?.length ?? 0} ${data.bom_changes?.length === 1 ? 'change' : 'changes'}`}</Text>
            </Text>
            <Icon name={changes ? 'chevron-up' : 'chevron-down'} size={16} />
          </Pressable>
          {changes ? (data.bom_changes?.length ? (
            <View style={{ gap: space(1.5) }}>
              {data.bom_changes.map((c) => <ChangeLine key={c.CHANGE_ID} c={c} describe={describe} />)}
            </View>
          ) : <Muted>Nothing differs from the revision before.</Muted>) : null}
        </Card>
      ) : null}

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), flexWrap: 'wrap' }}>
        <SearchBox value={query} onChangeText={setQuery} placeholder="Search item, category or sector" style={{ flex: 1, minWidth: 220, maxWidth: 420 }} />
        <Chips value={kind} onChange={setKind} options={[
          { key: 'ALL', label: 'All', count: lines.length }, { key: 'Install', label: 'Install', count: count('Install') }, { key: 'Remove', label: 'Remove', count: count('Remove') },
        ]} />
        {editable ? <Button small icon="plus" title="Add an item" onPress={() => onEdit('add')} /> : null}
      </View>
      {editable ? <Muted>This revision is still a draft. Each change you make asks for a reason, and is kept with who made it and when.</Muted> : null}
      <DataTable columns={columns} rows={all || query || kind !== 'ALL' ? rows : rows.slice(0, PAGE)} keyFor={(l, i) => l.LINE_ID ?? String(i)} minWidth={640}
        empty={<EmptyState icon="search" title="No items match" text="Change the search or the filter to see more." />} />
      {!all && !query && kind === 'ALL' && rows.length > PAGE ? <Button kind="secondary" icon="chevrons-down" title={`Show all ${rows.length} items`} onPress={() => setAll(true)} /> : null}
    </View>
  );
}

function ChangeLine({ c, describe }: { c: BomChange; describe: (c?: string | null) => string }) {
  const added = c.FROM_QTY === 0, removed = c.TO_QTY === 0;
  const word = added ? 'Added' : removed ? 'Removed' : 'Quantity changed';
  const tone = added ? colors.ok : removed ? colors.danger : colors.info;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), flexWrap: 'wrap', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border }}>
      <Badge text={word} color={tone} />
      <View style={{ flex: 1, minWidth: 200 }}>
        <Text style={{ fontSize: 13.5, fontWeight: '700', color: colors.text }} numberOfLines={1}>{c.model || c.CATALOG_KEY}</Text>
        <Muted numberOfLines={1}>{`${SECTOR[c.SECTOR ?? ''] ?? c.SECTOR ?? 'Site'}${c.REASONS?.length ? ` · ${c.REASONS.map((r) => describe(r)).join(', ')}` : ''}`}</Muted>
      </View>
      <Text style={{ fontSize: 13, color: colors.text }}>{added ? `${c.TO_QTY}` : removed ? `${c.FROM_QTY} → 0` : `${c.FROM_QTY} → ${c.TO_QTY}`}</Text>
    </View>
  );
}

// ------------------------------------------------------------------------------------------------ scope, drawings, history
function ScopePanel({ delta }: { delta: R[] }) {
  const sectors = [...new Set(delta.map((d) => d.SECTOR || 'SITE'))];
  const n = (...a: string[]) => delta.filter((d) => a.includes(act(d))).length;
  if (!delta.length) return <Card><EmptyState icon="layers" title="No scope of work yet" text="It appears here once the site has been scoped." /></Card>;
  return (
    <View style={{ gap: space(3) }}>
      <View style={{ flexDirection: 'row', gap: space(3), flexWrap: 'wrap' }}>
        <Stat label="To install" value={n('NEW', 'INSTALL')} icon="plus-circle" color={colors.ok} />
        <Stat label="To remove" value={n('REMOVED', 'REMOVE')} icon="minus-circle" color={n('REMOVED', 'REMOVE') ? colors.danger : undefined} />
        <Stat label="To move or reuse" value={n('RELOCATED', 'REUSED')} icon="repeat" />
        <Stat label="Stays as it is" value={n('EXISTING')} icon="check-circle" />
      </View>
      {sectors.map((sec) => (
        <Card key={sec} style={{ gap: space(1), padding: 0, overflow: 'hidden' }}>
          <View style={{ backgroundColor: colors.surfaceAlt, paddingHorizontal: space(4), paddingVertical: space(2.5), borderBottomWidth: 1, borderBottomColor: colors.border }}>
            <Text style={{ fontWeight: '700', fontSize: 13.5, color: colors.text }}>{sec === 'SITE' ? 'Whole site' : `Sector ${SECTOR[sec] ?? sec}`}</Text>
          </View>
          {delta.filter((d) => (d.SECTOR || 'SITE') === sec).map((d, i, all) => (
            <View key={d.SEQ ?? i} style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), flexWrap: 'wrap', paddingHorizontal: space(4), paddingVertical: space(2.5),
              borderBottomWidth: i < all.length - 1 ? 1 : 0, borderBottomColor: colors.border }}>
              <View style={{ flex: 1, minWidth: 220 }}>
                <Text style={{ fontSize: 13.5, fontWeight: '700', color: colors.text }}>
                  {[d.POSITION ? `Position ${d.POSITION}` : null, d.CATALOG_KEY || 'Equipment'].filter(Boolean).join(' · ')}
                </Text>
                {d.DESCRIPTION || d.KIND ? <Muted numberOfLines={1}>{d.DESCRIPTION || humanize(String(d.KIND))}</Muted> : null}
              </View>
              <Badge text={DELTA_TEXT[act(d)] ?? humanize(String(d.ACTION ?? ''))} color={DELTA_TONE[act(d)] ?? colors.neutral} />
            </View>
          ))}
        </Card>
      ))}
    </View>
  );
}

function DrawingsPanel({ docs, siteId, onView }: { docs: R[]; siteId: string; onView: (t: FilePreviewTarget) => void }) {
  if (!docs.length) return <Card><EmptyState icon="file-text" title="No drawings yet" text="The final construction drawings appear here once the site has been scoped." /></Card>;
  return (
    <Card style={{ gap: space(2.5) }}>
      <Muted>The construction drawings that go to the service provider: the current revision, with the redlined drawing where changes were needed.</Muted>
      {docs.map((d) => {
        const folder = d.DOC_TYPE === 'CD_REDLINE' ? 'redlines' : 'cds';
        return (
          <View key={d.DOC_ID || d.FILE_NAME} style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), flexWrap: 'wrap', padding: space(3), borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceAlt }}>
            <IconBadge name="file-text" size={34} />
            <View style={{ flex: 1, minWidth: 200, gap: 2 }}>
              <Text style={{ fontSize: 13.5, fontWeight: '700', color: colors.text }} numberOfLines={1}>{d.FILE_NAME}</Text>
              <View style={{ flexDirection: 'row', gap: space(2), alignItems: 'center' }}>
                <Badge text={d.DOC_TYPE === 'CD_REDLINE' ? 'Redlined' : d.REVISION ? `Drawing ${d.REVISION}` : 'Current'} color={d.DOC_TYPE === 'CD_REDLINE' ? colors.warn : colors.ok} />
                {d.SIZE_BYTES ? <Muted>{`${Math.max(1, Math.round(d.SIZE_BYTES / 1024))} KB`}</Muted> : null}
              </View>
            </View>
            <Row style={{ gap: space(2) }}>
              <Button small icon="eye" title="View" onPress={() => onView({ name: d.FILE_NAME, folder, siteId, docId: d.DOC_ID, size: d.SIZE_BYTES })} />
              <Button small kind="secondary" icon="download" title="Download"
                onPress={() => Linking.openURL(authedUrl(`/sharepoint/sites/${siteId}/files/download?folder=${folder}&file_name=${encodeURIComponent(d.FILE_NAME)}`))} />
            </Row>
          </View>
        );
      })}
    </Card>
  );
}

function HistoryPanel({ events, describe, me }: { events: R[]; describe: (c?: string | null) => string; me?: string }) {
  if (!events.length) return <Card><EmptyState icon="clock" title="Nothing yet" text="Each step taken on the package is listed here, with who took it and when." /></Card>;
  return (
    <Card style={{ gap: 0 }}>
      {events.map((e, i) => (
        <View key={e.EVENT_ID ?? i} style={{ flexDirection: 'row', gap: space(3), paddingVertical: space(3), borderBottomWidth: i < events.length - 1 ? 1 : 0, borderBottomColor: colors.border }}>
          <View style={{ alignItems: 'center', paddingTop: 4 }}><View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: colors.accent }} /></View>
          <View style={{ flex: 1, gap: 3 }}>
            <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{HISTORY_COPY[e.ACTION] ?? humanize(String(e.ACTION))}</Text>
            {e.REASON_CODE ? <Text style={{ fontSize: 13, color: colors.accent, fontWeight: '600' }}>{describe(e.REASON_CODE)}</Text> : null}
            {e.COMMENT ? <Text style={{ fontSize: 13, color: colors.text, lineHeight: 19 }}>{`“${e.COMMENT}”`}</Text> : null}
            <Muted>{[e.ACTOR_USER_ID && e.ACTOR_USER_ID === me ? 'You' : e.ACTOR_ROLE ? roleLabel(e.ACTOR_ROLE) : null, when(e.EVENT_TS)].filter(Boolean).join(' · ')}</Muted>
          </View>
        </View>
      ))}
    </Card>
  );
}

// ------------------------------------------------------------------------------------------------ dialogs
/** A step that moves the package on: says what it does first; asks for a reason and the user's own words only when that step needs them. */
function StepDialog({ step, siteId, provider, rev, onClose, onDone }: { step: WorkflowAction | null; siteId: string; provider: string; rev: string; onClose: () => void; onDone: () => void }) {
  const codes = useReasonCodes(step ? [`SITE_SCOPING:${step.action}`, 'SITE_SCOPING'] : undefined);
  const [reason, setReason] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const copy = step ? STEP_COPY[step.action] : undefined;
  const close = () => { setReason(null); setComment(''); setErr(null); onClose(); };
  const go = async () => {
    if (!step) return;
    setBusy(true); setErr(null);
    try {
      await api.post(`/workflow/SITE_SCOPING/${siteId}/transition`, { action: step.action, reason_code: reason, comment: comment.trim() || null });
      setReason(null); setComment('');
      onDone();
    } catch (e) { setErr(e as ApiError); } finally { setBusy(false); }
  };
  const needsReason = !!step?.requires_reason, needsComment = !!step?.requires_comment;
  return (
    <Dialog open={!!step} onClose={close} title={copy?.label ?? (step ? humanize(step.action) : '')}
      footer={<>
        <Button kind="secondary" small title="Cancel" onPress={close} />
        <Button small kind={copy?.kind === 'danger' ? 'danger' : 'primary'} title={busy ? 'Saving…' : copy?.label ?? 'Confirm'}
          disabled={busy || (needsReason && !reason) || (needsComment && !comment.trim())} onPress={go} />
      </>}>
      <View style={{ gap: space(3) }}>
        <Text style={[s.body, { color: colors.muted, lineHeight: 21 }]}>{copy?.what(provider, rev) ?? step?.description}</Text>
        {needsReason ? (
          <View style={{ gap: 6, zIndex: 10 }}>
            <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.text }}>Why? (required)</Text>
            <Select value={reason} onChange={setReason} placeholder="Choose a reason" width={480} options={codes.map((c) => ({ key: c.REASON_CODE, label: c.DESCRIPTION || c.REASON_CODE }))} />
          </View>
        ) : null}
        {needsReason || needsComment ? (
          <View style={{ gap: 6 }}>
            <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.text }}>{needsComment ? 'Your comment (required)' : 'Your comment (optional)'}</Text>
            <TextInput style={[s.input, { minHeight: 76 }]} multiline value={comment} onChangeText={setComment} placeholder="Say what you want the next person to know" />
          </View>
        ) : null}
        {err ? <ErrorView error={err} /> : null}
      </View>
    </Dialog>
  );
}

function ProviderDialog({ open, siteId, current, onClose, onDone }: { open: boolean; siteId: string; current?: string | null; onClose: () => void; onDone: () => void }) {
  const list = useApi<{ name: string }[]>(open ? '/sites/service-providers' : null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const pick = async (name: string) => {
    setBusy(true); setErr(null);
    try { await api.post(`/sites/${siteId}/assign-sp`, { cx_sp: name }); onDone(); } catch (e) { setErr(e as ApiError); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onClose={onClose} title="Service provider for this site" width={460} footer={<Button kind="secondary" small title="Close" onPress={onClose} />}>
      <View style={{ gap: space(2) }}>
        <Muted>The company that will build this site. Only this company sees the package once it is sent.</Muted>
        {list.data && !list.data.length ? <Banner kind="info" title="No service providers yet">An admin adds them under User logins.</Banner> : null}
        {(list.data ?? []).map((p) => {
          const on = current === p.name;
          return (
            <Pressable key={p.name} disabled={busy} onPress={() => pick(p.name)}
              style={({ hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: space(3.5), borderRadius: radius.lg, borderWidth: 1,
                borderColor: on || hovered ? colors.accent : colors.border, backgroundColor: on ? colors.soft : '#fff' })}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{clean(p.name)}</Text>
              {on ? <Badge text="Chosen" color={colors.ok} /> : <Icon name="chevron-right" size={16} />}
            </Pressable>
          );
        })}
        {err ? <ErrorView error={err} /> : null}
      </View>
    </Dialog>
  );
}

/** Change, add or remove one item of a draft BOM. Every one needs a reason from the list; the server keeps who, when and why. */
function LineDialog({ edit, rev, onClose, onDone }: { edit: { mode: 'edit' | 'add' | 'remove'; line?: R }; rev: BomRevisionInfo; onClose: () => void; onDone: () => void }) {
  const l = edit.line;
  const codes = useReasonCodes('BOM_LINE');
  const [design, setDesign] = useState(String(l?.DESIGN_QTY ?? '1'));
  const [spare, setSpare] = useState(String(l?.SPARE_QTY ?? '0'));
  const [key, setKey] = useState('');
  const [sector, setSector] = useState('SITE');
  const [reason, setReason] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const catalog = useApi<R[]>(edit.mode === 'add' ? '/reference/material_catalog' : null);
  const [search, setSearch] = useState('');
  const matches = (catalog.data ?? []).filter((c) => search.trim().length > 1 && `${c.CATALOG_KEY} ${c.MODEL} ${c.DESCRIPTION}`.toLowerCase().includes(search.trim().toLowerCase())).slice(0, 5);
  const chosen = (catalog.data ?? []).find((c) => c.CATALOG_KEY === key);
  const title = edit.mode === 'edit' ? `Change ${l?.MODEL ?? 'item'}` : edit.mode === 'remove' ? `Remove ${l?.MODEL ?? 'item'}` : 'Add an item';

  const save = async () => {
    setBusy(true); setErr(null);
    try {
      const why = { reason_code: reason, comment: comment.trim() || null };
      if (edit.mode === 'edit') await api.patch(`/bom/lines/${l!.LINE_ID}`, { design_qty: Number(design), spare_qty: Number(spare), ...why });
      else if (edit.mode === 'remove') await api.del(`/bom/lines/${l!.LINE_ID}?reason_code=${encodeURIComponent(reason ?? '')}${comment.trim() ? `&comment=${encodeURIComponent(comment.trim())}` : ''}`);
      else await api.post(`/bom/revisions/${rev.id}/lines`, { sector, catalog_key: key, design_qty: Number(design), spare_qty: Number(spare), ...why });
      onDone();
    } catch (e) { setErr(e as ApiError); } finally { setBusy(false); }
  };
  const bad = (v: string) => !v.trim() || Number.isNaN(Number(v)) || Number(v) < 0;
  return (
    <Dialog open onClose={onClose} title={title} footer={<>
      <Button kind="secondary" small title="Cancel" onPress={onClose} />
      <Button small kind={edit.mode === 'remove' ? 'danger' : 'primary'} title={busy ? 'Saving…' : edit.mode === 'remove' ? 'Remove' : 'Save'}
        disabled={busy || !reason || (edit.mode !== 'remove' && (bad(design) || bad(spare))) || (edit.mode === 'add' && !key)} onPress={save} />
    </>}>
      <View style={{ gap: space(3) }}>
        {edit.mode === 'remove' ? <Muted>{`This takes the item out of ${rev.label}. The earlier revisions are not touched.`}</Muted> : null}
        {edit.mode === 'add' ? (
          <View style={{ gap: space(2) }}>
            <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.text }}>Item</Text>
            {chosen ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: space(3), borderRadius: radius.md, backgroundColor: colors.soft }}>
                <View style={{ flex: 1 }}><Text style={{ fontWeight: '700', color: colors.text }}>{chosen.MODEL}</Text><Muted numberOfLines={1}>{chosen.DESCRIPTION}</Muted></View>
                <IconButton icon="x" label="Choose another" onPress={() => { setKey(''); setSearch(''); }} />
              </View>
            ) : (
              <>
                <SearchBox value={search} onChangeText={setSearch} placeholder="Search by model or description" />
                {matches.map((c) => (
                  <Pressable key={c.CATALOG_KEY} onPress={() => setKey(c.CATALOG_KEY)} style={({ hovered }: any) => ({ padding: space(2.5), borderRadius: radius.md, backgroundColor: hovered ? colors.surfaceAlt : undefined })}>
                    <Text style={{ fontWeight: '700', color: colors.text }}>{c.MODEL}</Text><Muted numberOfLines={1}>{c.DESCRIPTION}</Muted>
                  </Pressable>
                ))}
              </>
            )}
            <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.text }}>Sector</Text>
            <Chips value={sector} onChange={setSector} options={['A', 'B', 'C', 'D', 'SITE'].map((k) => ({ key: k, label: k === 'SITE' ? 'Whole site' : SECTOR[k] }))} />
          </View>
        ) : null}
        {edit.mode !== 'remove' ? (
          <Row style={{ gap: space(3) }}>
            <View style={{ flex: 1, gap: 6 }}>
              <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.text }}>Quantity needed</Text>
              <TextInput style={s.input} keyboardType="numeric" value={design} onChangeText={setDesign} />
            </View>
            <View style={{ flex: 1, gap: 6 }}>
              <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.text }}>Spares</Text>
              <TextInput style={s.input} keyboardType="numeric" value={spare} onChangeText={setSpare} />
            </View>
          </Row>
        ) : null}
        <View style={{ gap: 6, zIndex: 10 }}>
          <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.text }}>Why? (required)</Text>
          <Select value={reason} onChange={setReason} placeholder="Choose a reason" width={480} options={codes.map((c) => ({ key: c.REASON_CODE, label: c.DESCRIPTION || c.REASON_CODE }))} />
        </View>
        <View style={{ gap: 6 }}>
          <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.text }}>Comment (optional)</Text>
          <TextInput style={[s.input, { minHeight: 60 }]} multiline value={comment} onChangeText={setComment} />
        </View>
        {err ? <ErrorView error={err} /> : null}
      </View>
    </Dialog>
  );
}
