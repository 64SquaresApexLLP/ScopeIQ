// Redlines and RFIs in one workspace, for the whole program (the sidebar page) or for one site (the site tab).
// What each role is offered comes from the server's action lists, so a role sees buttons only for what it may do.
import { router } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Image, Linking, Modal, Platform, Pressable, ScrollView, Text, TextInput, View, useWindowDimensions } from 'react-native';
import { api, ApiError, authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { label, roleLabel, when } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, radius, shadow, space, tint } from '../theme';
import { Badge, Button, Card, Chips, Dialog, EmptyState, ErrorView, Icon, IconBadge, Loading, Muted, Select, SearchBox, SegmentedTabs, Stat } from '../ui';
import { WorkflowActions } from '../WorkflowActions';

// ------------------------------------------------------------------ evidence (also used by the finding page and the BOM screens)
/** The drone footage that backs a redline: the video frame (or still) that looks at the place the redline is about. */
export function ProofStrip({ proof }: { proof: R[] }) {
  const [big, setBig] = useState<R | null>(null);
  const sheet = proof.find((p) => p.KIND === 'SHEET');       // the drawing sheet with this redline marked
  const drone = proof.filter((p) => p.KIND !== 'SHEET');
  return (
    <View style={{ marginTop: space(3), gap: space(3) }}>
      {sheet ? (
        <View style={{ gap: space(2) }}>
          <Muted style={{ fontWeight: '700', color: colors.text }}>Sheet with this redline marked</Muted>
          <Pressable onPress={() => setBig(sheet)} accessibilityRole="button" accessibilityLabel={`Enlarge: ${sheet.CAPTION}`} style={{ maxWidth: 760 }}>
            <Image source={{ uri: authedUrl(sheet.URL) }} resizeMode="contain" style={{ width: '100%', aspectRatio: 1224 / 792, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: '#fff' }} />
          </Pressable>
          <Muted>{`${sheet.CAPTION}. Tap to enlarge.`}</Muted>
        </View>
      ) : null}
      {!drone.length ? <Muted>No drone footage faces this place, so there is no picture to attach.</Muted> : (
        <View style={{ gap: space(2) }}>
          <Muted style={{ fontWeight: '700', color: colors.text }}>Proof from the drone survey</Muted>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', gap: space(3) }}>
            {drone.map((p) => (
              <Pressable key={p.PROOF_ID} onPress={() => setBig(p)} accessibilityRole="button" accessibilityLabel={`Enlarge: ${p.CAPTION}`} style={{ width: 280, gap: 4 }}>
                <Image source={{ uri: authedUrl(p.URL) }} resizeMode="cover" style={{ width: 280, height: 158, borderRadius: 10, backgroundColor: colors.border }} />
                <Badge text={p.KIND === 'VIDEO' ? 'Drone video' : 'Drone still'} />
                <Muted style={{ color: colors.text, fontWeight: '600' }}>{p.CAPTION}</Muted>
                <Muted>{p.BASIS}</Muted>
              </Pressable>
            ))}
          </View>
        </View>
      )}
      <Modal visible={!!big} transparent animationType="fade" onRequestClose={() => setBig(null)}>
        <Pressable onPress={() => setBig(null)} style={{ flex: 1, backgroundColor: '#000d', justifyContent: 'center', alignItems: 'center', padding: space(4) }}>
          {big ? <Image source={{ uri: authedUrl(big.URL) }} resizeMode="contain" style={{ width: '100%', height: '85%' }} /> : null}
          <Muted style={{ color: '#fff', marginTop: space(2) }}>{big ? `${big.CAPTION}  -  tap anywhere to close` : ''}</Muted>
        </Pressable>
      </Modal>
    </View>
  );
}

/** The red-marked drawing shown in the page, so it does not have to be downloaded to be read. */
export function PdfPreview({ path, startOpen = true }: { path: string; startOpen?: boolean }) {
  const [open, setOpen] = useState(startOpen);
  const url = authedUrl(path);
  const name = decodeURIComponent(path.split('/').pop()?.split('?')[0] ?? 'Redlined drawing');
  return (
    <Card style={{ marginBottom: space(3) }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
        <View style={{ flexDirection: 'row', flex: 1, minWidth: 220, gap: space(3), alignItems: 'center' }}>
          <IconBadge name="file-text" color={colors.danger} size={40} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>Redlined drawing</Text>
            <Muted numberOfLines={1}>{name}</Muted>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: space(2) }}>
          <Button small kind="secondary" title={open ? 'Hide preview' : 'Show preview'} onPress={() => setOpen((v) => !v)} />
          <Button small title="Open in new tab" onPress={() => Linking.openURL(url)} />
        </View>
      </View>
      {open ? (
        Platform.OS === 'web' ? (
          <View style={{ marginTop: space(3) }}>
            {React.createElement('iframe', {
              src: `${url}#view=FitH&navpanes=0`, title: 'Redlined drawing preview',
              style: { width: '100%', height: 780, border: `1px solid ${colors.border}`, borderRadius: 12, backgroundColor: '#fff' },
            })}
          </View>
        ) : (
          <Muted style={{ marginTop: space(2) }}>The preview is shown in the browser. Use "Open in new tab" on this device.</Muted>
        )
      ) : null}
    </Card>
  );
}

// ------------------------------------------------------------------ status
const RED_GROUPS: Record<string, string[]> = {
  IN_REVIEW: ['IN_REVIEW', 'APPROVED', 'SENT_TO_AE', 'DRAFT'], WORK_QUEUE: ['WORK_QUEUE', 'ACKNOWLEDGED'], COMPLETED: ['COMPLETED', 'INCORPORATED', 'CLOSED'], REJECTED: ['REJECTED'],
};
const redGroup = (st: string) => Object.keys(RED_GROUPS).find((k) => RED_GROUPS[k].includes(st)) ?? st;
const RED_META: Record<string, { text: string; color: string; step: number }> = {
  IN_REVIEW: { text: 'In review', color: colors.warn, step: 1 }, WORK_QUEUE: { text: 'Work queue', color: colors.info, step: 2 },
  COMPLETED: { text: 'Completed', color: colors.ok, step: 3 }, REJECTED: { text: 'Rejected', color: colors.danger, step: 3 },
};
const RFI_META: Record<string, { text: string; color: string; step: number }> = {
  DRAFT: { text: 'Draft', color: colors.neutral, step: 0 }, SUBMITTED: { text: 'Sent', color: colors.info, step: 1 }, IN_REVIEW: { text: 'In review', color: colors.warn, step: 2 },
  ANSWERED: { text: 'Answered', color: colors.ok, step: 3 }, CLOSED: { text: 'Closed', color: colors.ok, step: 4 },
};
const redMeta = (st: string) => RED_META[redGroup(st)] ?? { text: label(st), color: colors.neutral, step: 0 };
const rfiMeta = (st: string) => RFI_META[st] ?? { text: label(st), color: colors.neutral, step: 0 };
const ago = (iso?: string | null) => {
  if (!iso) return '';
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return d <= 0 ? 'Today' : d === 1 ? '1 day ago' : `${d} days ago`;
};
const stamp = (x: R) => String(x.SUBMITTED_AT || x.CREATED_AT || x.UPDATED_AT || '');

/** Where an item is on its way, one dot per step. */
function Stepper({ steps, current, failedAt }: { steps: string[]; current: number; failedAt?: number }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
      {steps.map((t, i) => {
        const failed = failedAt === i;
        const done = !failed && i <= current;
        const c = failed ? colors.danger : done ? colors.accent : colors.faint;
        return (
          <React.Fragment key={t}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <View style={{ width: 18, height: 18, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: done || failed ? c : '#fff', borderWidth: 1.5, borderColor: c }}>
                {done || failed ? <Icon name={failed ? 'x' : 'check'} size={11} color="#fff" /> : null}
              </View>
              <Text style={{ fontSize: 12, fontWeight: i === current || failed ? '700' : '500', color: done || failed ? colors.text : colors.faint }}>{t}</Text>
            </View>
            {i < steps.length - 1 ? <View style={{ width: 18, height: 1.5, backgroundColor: done && i < current ? colors.accent : colors.border }} /> : null}
          </React.Fragment>
        );
      })}
    </View>
  );
}

function Timeline({ items }: { items: { title: string; who?: string | null; at?: string | null; note?: string | null; color?: string }[] }) {
  if (!items.length) return null;
  return (
    <View style={{ gap: space(3), marginTop: space(1) }}>
      {items.map((e, i) => (
        <View key={i} style={{ flexDirection: 'row', gap: space(3) }}>
          <View style={{ alignItems: 'center' }}>
            <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: e.color ?? colors.accent, marginTop: 4 }} />
            {i < items.length - 1 ? <View style={{ width: 1.5, flex: 1, backgroundColor: colors.border, marginTop: 2 }} /> : null}
          </View>
          <View style={{ flex: 1, paddingBottom: 2 }}>
            <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{e.title}</Text>
            <Text style={{ fontSize: 12, color: colors.muted, marginTop: 1 }}>{[e.who, e.at ? when(e.at) : null].filter(Boolean).join('  ·  ')}</Text>
            {e.note ? <Text style={{ fontSize: 12.5, color: colors.text, fontStyle: 'italic', marginTop: 3 }}>"{e.note}"</Text> : null}
          </View>
        </View>
      ))}
    </View>
  );
}

function Panel({ title, icon, children, tone }: { title: string; icon: React.ComponentProps<typeof Icon>['name']; children: React.ReactNode; tone?: keyof typeof tint }) {
  const t = tone ? tint[tone] : null;
  return (
    <View style={{ borderWidth: 1, borderColor: t ? t.line : colors.border, backgroundColor: t ? t.bg : '#fff', borderRadius: radius.lg, padding: space(4), gap: space(2) }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2) }}>
        <Icon name={icon} size={14} color={t ? t.fg : colors.muted} />
        <Text style={{ fontSize: 11.5, fontWeight: '700', letterSpacing: 0.6, color: t ? t.fg : colors.muted, textTransform: 'uppercase' }}>{title}</Text>
      </View>
      {children}
    </View>
  );
}

const SiteLink = ({ id }: { id: string }) => (
  <Pressable onPress={() => router.push({ pathname: '/site/[id]', params: { id, tab: 'redlines' } })} accessibilityRole="link"
    style={({ hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: 4, opacity: hovered ? 0.7 : 1 })}>
    <Icon name="map-pin" size={13} color={colors.accent} />
    <Text style={{ color: colors.accent, fontWeight: '600', fontSize: 13 }}>{id}</Text>
  </Pressable>
);

// ------------------------------------------------------------------ a redline
function RedlineDetail({ x, reload, showSite }: { x: R; reload: () => void; showSite: boolean }) {
  const { user } = useAuth();
  const meta = redMeta(x.STATUS);
  const group = redGroup(x.STATUS);
  const actions: string[] = x.ACTIONS ?? [];
  const canIssue = ['AE_ENGINEER', 'ADMIN'].includes(user?.role ?? '') && group !== 'COMPLETED' && group !== 'REJECTED';
  const hint: Record<string, string> = {
    REVIEW_DONE: 'confirms you have checked it against the evidence below.',
    COMPLETE: 'issues the corrected drawing as the next drawing revision of this site.',
    REJECT: 'sends it back with your reason, if the redline is not right.',
  };
  const waiting =
    group === 'IN_REVIEW' ? 'Waiting for the A&E engineer to review this redline.' :
    group === 'WORK_QUEUE' ? 'Reviewed. The A&E engineer is preparing the corrected drawing.' :
    group === 'COMPLETED' ? 'The corrected drawing has been issued.' :
    `Rejected${x.REJECTED_REASON ? `: ${x.REJECTED_REASON}` : ''}.`;
  const events = [
    { title: 'Redline raised', who: x.SUBMITTED_BY ? `${x.SUBMITTED_BY} (${roleLabel(x.SUBMITTED_ROLE)})` : null, at: x.SUBMITTED_AT, color: colors.muted },
    x.REVIEWED_BY ? { title: 'Reviewed', who: `${x.REVIEWED_BY} (${roleLabel(x.REVIEWED_ROLE)})`, at: x.REVIEWED_AT, note: x.REVIEWED_COMMENT, color: colors.info } : null,
    x.COMPLETED_BY ? { title: 'Completed, corrected drawing issued', who: `${x.COMPLETED_BY} (${roleLabel(x.COMPLETED_ROLE)})`, at: x.COMPLETED_AT, note: x.COMPLETED_COMMENT, color: colors.ok } : null,
    x.REJECTED_BY ? { title: `Rejected${x.REJECTED_REASON ? ` · ${x.REJECTED_REASON}` : ''}`, who: `${x.REJECTED_BY} (${roleLabel(x.REJECTED_ROLE)})`, at: x.REJECTED_AT, note: x.REJECTED_COMMENT, color: colors.danger } : null,
  ].filter(Boolean) as { title: string; who?: string | null; at?: string | null; note?: string | null; color?: string }[];

  return (
    <View style={[{ backgroundColor: '#fff', borderRadius: radius.xl, borderWidth: 1, borderColor: colors.border, padding: space(5), gap: space(4) }, shadow as any]}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: space(3), flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 220, gap: 4 }}>
          {showSite ? <SiteLink id={x.SITE_ID} /> : null}
          <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text, letterSpacing: -0.2 }}>{`${x.DOC_TYPE} ${x.DOC_REVISION ?? ''} · sheet ${x.SHEET}`}</Text>
        </View>
        <Badge text={meta.text} color={meta.color} dot />
      </View>
      <Stepper steps={['Raised', 'In review', 'Work queue', group === 'REJECTED' ? 'Rejected' : 'Completed']} current={meta.step} failedAt={group === 'REJECTED' ? 3 : undefined} />

      <Text style={{ fontSize: 15, fontWeight: '600', color: colors.text, lineHeight: 22 }}>{x.MARKUP}</Text>
      <View style={{ flexDirection: 'row', gap: space(3), flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 200, padding: space(3), borderRadius: radius.md, backgroundColor: tint.danger.bg, borderWidth: 1, borderColor: tint.danger.line }}>
          <Text style={{ fontSize: 11, fontWeight: '700', letterSpacing: 0.6, color: tint.danger.fg }}>DRAWING SHOWS</Text>
          <Text style={{ fontSize: 14, color: colors.text, marginTop: 4 }}>{x.CHANGE_FROM || 'Nothing recorded'}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 200, padding: space(3), borderRadius: radius.md, backgroundColor: tint.ok.bg, borderWidth: 1, borderColor: tint.ok.line }}>
          <Text style={{ fontSize: 11, fontWeight: '700', letterSpacing: 0.6, color: tint.ok.fg }}>FIELD (DRONE) SHOWS</Text>
          <Text style={{ fontSize: 14, color: colors.text, marginTop: 4 }}>{x.CHANGE_TO || 'Nothing recorded'}</Text>
        </View>
      </View>

      {/* what this role can do now */}
      {actions.length || canIssue ? (
        <Panel title="Your action" icon="check-square" tone="info">
          {actions.map((a) => hint[a] ? <Text key={a} style={{ fontSize: 12.5, color: colors.text }}>{`${label(a)} ${hint[a]}`}</Text> : null)}
          <View style={{ flexDirection: 'row', gap: space(2), flexWrap: 'wrap', alignItems: 'center', marginTop: space(1) }}>
            {actions.length ? <WorkflowActions actions={actions} endpoint={`/redlines/${x.REDLINE_ID}/transition`} entity="REDLINE" onDone={reload} /> : null}
            {canIssue ? <Button small kind="secondary" icon="upload-cloud" title="Upload corrected drawing" onPress={() => router.push({ pathname: '/(tabs)/sharepoint', params: { site: x.SITE_ID } })} /> : null}
          </View>
        </Panel>
      ) : (
        <Panel title="Status" icon="info"><Text style={{ fontSize: 13, color: colors.text }}>{waiting}</Text></Panel>
      )}

      {x.PDF_URL ? (
        <View style={{ flexDirection: 'row', gap: space(2), flexWrap: 'wrap' }}>
          <Button small kind="secondary" icon="file-text" title="Open redlined drawing (PDF)" onPress={() => Linking.openURL(authedUrl(x.PDF_URL))} />
        </View>
      ) : null}
      {Array.isArray(x.PROOF) && x.PROOF.length ? <ProofStrip proof={x.PROOF} /> : null}
      <Panel title="Activity" icon="clock"><Timeline items={events} /></Panel>
    </View>
  );
}

// ------------------------------------------------------------------ an RFI
function RfiDetail({ r, reload, showSite }: { r: R; reload: () => void; showSite: boolean }) {
  const { user, can } = useAuth();
  const [answer, setAnswer] = useState(r.PROPOSED_ANSWER ?? '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const meta = rfiMeta(r.STATUS);
  const toAe = r.TO_PARTY === 'AE_ENGINEER';
  const target = toAe ? user?.role === 'AE_ENGINEER' : can('ADMIN', 'ERICSSON');
  const canAnswer = r.STATUS === 'IN_REVIEW' && target;
  const actions: string[] = (r.ACTIONS ?? []).filter((a: string) => a !== 'ANSWER');
  const hint: Record<string, string> = {
    START_REVIEW: 'takes this RFI so you can answer it.',
    SUBMIT: 'sends the RFI to its recipient.',
    CLOSE: 'closes the RFI once the answer has been applied.',
  };
  const send = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.post(`/rfis/${r.RFI_ID}/answer`, { answer });
      reload();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  const findings: string[] = Array.isArray(r.DISC_IDS) ? r.DISC_IDS : [];
  const scoping = !['AE_ENGINEER', 'CX_SP'].includes(user?.role ?? '');
  return (
    <View style={[{ backgroundColor: '#fff', borderRadius: radius.xl, borderWidth: 1, borderColor: colors.border, padding: space(5), gap: space(4) }, shadow as any]}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: space(3), flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 220, gap: 4 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
            {showSite ? <SiteLink id={r.SITE_ID} /> : null}
            <Badge text={toAe ? 'To A&E engineer' : 'To Admin'} color={colors.neutral} />
          </View>
          <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text, letterSpacing: -0.2 }}>{r.SUBJECT}</Text>
        </View>
        <Badge text={meta.text} color={meta.color} dot />
      </View>
      <Stepper steps={['Draft', 'Sent', 'In review', 'Answered', 'Closed']} current={meta.step} />

      <Panel title="Question" icon="help-circle"><Text style={{ fontSize: 14, color: colors.text, lineHeight: 21 }}>{r.QUESTION}</Text></Panel>
      {r.PROPOSED_ANSWER && !r.ANSWER ? <Panel title="Proposed answer" icon="edit-3"><Text style={{ fontSize: 14, color: colors.text, lineHeight: 21 }}>{r.PROPOSED_ANSWER}</Text></Panel> : null}
      {r.ANSWER ? <Panel title="Answer" icon="check-circle" tone="ok"><Text style={{ fontSize: 14, color: colors.text, lineHeight: 21 }}>{r.ANSWER}</Text></Panel> : null}

      {canAnswer ? (
        <Panel title="Your answer" icon="message-square" tone="info">
          <TextInput style={{ minHeight: 84, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, padding: space(3), backgroundColor: '#fff', fontSize: 14, color: colors.text }}
            multiline placeholder="Type the answer" placeholderTextColor="#A9B3C2" value={answer} onChangeText={setAnswer} />
          <View style={{ flexDirection: 'row', justifyContent: 'flex-end' }}>
            <Button small title={busy ? 'Sending...' : 'Send answer'} disabled={!answer.trim() || busy} onPress={send} />
          </View>
          {err ? <ErrorView error={err} /> : null}
        </Panel>
      ) : r.STATUS === 'IN_REVIEW' ? (
        <Panel title="Status" icon="clock"><Text style={{ fontSize: 13, color: colors.text }}>{`Waiting for ${toAe ? 'the A&E engineer' : 'Admin'} to answer.`}</Text></Panel>
      ) : null}

      {actions.length ? (
        <Panel title="Your action" icon="check-square" tone="info">
          {actions.map((a) => hint[a] ? <Text key={a} style={{ fontSize: 12.5, color: colors.text }}>{`${label(a)} ${hint[a]}`}</Text> : null)}
          <View style={{ marginTop: space(1) }}><WorkflowActions actions={actions} endpoint={`/rfis/${r.RFI_ID}/transition`} entity="RFI" onDone={reload} /></View>
        </Panel>
      ) : null}

      {scoping && findings.length ? (
        <Panel title="Raised from" icon="alert-triangle">
          <View style={{ flexDirection: 'row', gap: space(2), flexWrap: 'wrap' }}>
            {findings.map((id) => <Button key={id} small kind="secondary" title="Open finding" onPress={() => router.push({ pathname: '/discrepancy/[id]', params: { id } })} />)}
          </View>
        </Panel>
      ) : null}
      {r.UPDATED_BY ? <Muted>{`Last updated by ${r.UPDATED_BY}${r.UPDATED_AT ? `, ${when(r.UPDATED_AT)}` : ''}`}</Muted> : null}
    </View>
  );
}

// ------------------------------------------------------------------ the workspace
type Section = 'REDLINES' | 'RFIS';
type Sort = 'NEW' | 'OLD' | 'SITE';

export function RedlinesRfisWorkspace({ siteId }: { siteId?: string }) {
  const { user, can } = useAuth();
  const role = user?.role ?? '';
  const q = siteId ? `?site_id=${siteId}` : '';
  const redlines = useApi<R[]>(`/redlines${q}`);
  const rfis = useApi<R[]>(`/rfis${q}`);
  const { width } = useWindowDimensions();
  const wide = width >= 1100;
  const [section, setSection] = useState<Section>('REDLINES');
  const [filter, setFilter] = useState<string>('ALL');
  const [recipient, setRecipient] = useState<'ALL' | 'ADMIN' | 'AE_ENGINEER'>('ALL');
  const [sort, setSort] = useState<Sort>('NEW');
  const [query, setQuery] = useState('');
  const [sel, setSel] = useState<string | null>(null);

  const redList = redlines.data ?? [];
  const rfiAll = rfis.data ?? [];
  const reload = () => { void redlines.reload(); void rfis.reload(); };
  const isMine = (r: R) => (section === 'REDLINES' ? (r.ACTIONS ?? []).length > 0 : (r.STATUS === 'IN_REVIEW' && (r.TO_PARTY === 'AE_ENGINEER' ? role === 'AE_ENGINEER' : can('ADMIN', 'ERICSSON'))) || (r.ACTIONS ?? []).some((a: string) => a !== 'ANSWER'));

  const rfiList = useMemo(() => rfiAll.filter((r) => recipient === 'ALL' || (recipient === 'AE_ENGINEER' ? r.TO_PARTY === 'AE_ENGINEER' : r.TO_PARTY !== 'AE_ENGINEER')), [rfiAll, recipient]);
  const items = section === 'REDLINES' ? redList : rfiList;
  const counts = useMemo(() => {
    const c: Record<string, number> = { ALL: items.length, MINE: items.filter(isMine).length };
    for (const x of items) {
      const k = section === 'REDLINES' ? redGroup(x.STATUS) : (x.STATUS === 'CLOSED' ? 'ANSWERED' : x.STATUS);
      c[k] = (c[k] ?? 0) + 1;
    }
    return c;
  }, [items, section, role]);

  const visible = useMemo(() => {
    let list = items.filter((x) => filter === 'ALL' ? true : filter === 'MINE' ? isMine(x) : section === 'REDLINES' ? redGroup(x.STATUS) === filter : (x.STATUS === 'CLOSED' ? 'ANSWERED' : x.STATUS) === filter);
    const t = query.trim().toLowerCase();
    if (t) list = list.filter((x) => [x.SITE_ID, x.MARKUP, x.SHEET, x.DOC_TYPE, x.SUBJECT, x.QUESTION].some((v) => String(v ?? '').toLowerCase().includes(t)));
    return [...list].sort((a, b) => sort === 'SITE' ? String(a.SITE_ID).localeCompare(String(b.SITE_ID)) : sort === 'OLD' ? stamp(a).localeCompare(stamp(b)) : stamp(b).localeCompare(stamp(a)));
  }, [items, filter, query, sort, section, role]);

  const idOf = (x: R) => (section === 'REDLINES' ? x.REDLINE_ID : x.RFI_ID);
  const current = visible.find((x) => idOf(x) === sel) ?? (wide ? visible[0] : undefined);
  const open = (id: string) => setSel(id);

  const guide: Record<string, Record<Section, string>> = {
    AE_ENGINEER: { REDLINES: 'Check each redline against the drone evidence, then mark it reviewed, complete it with the corrected drawing, or reject it with a reason.', RFIS: 'Answer the RFIs addressed to your firm.' },
    SCOPER: { REDLINES: 'The redlines raised from your findings, and where each one stands with the A&E engineer.', RFIS: 'Send your RFI drafts when they are ready, and follow the answers.' },
    REVIEWER: { REDLINES: 'Follow every redline to completion before it counts as resolved.', RFIS: 'Approve RFIs before they go out, and close them once answered.' },
    ADMIN: { REDLINES: 'Every redline, from raised to the corrected drawing.', RFIS: 'Answer the RFIs addressed to Admin, and close the ones that are answered.' },
  };
  const tip = (guide[role] ?? guide.ADMIN)[section];

  const filterOptions = section === 'REDLINES'
    ? [{ key: 'ALL', label: 'All', count: counts.ALL }, ...(counts.MINE || ['AE_ENGINEER', 'ADMIN'].includes(role) ? [{ key: 'MINE', label: 'Needs my action', count: counts.MINE }] : []),
       { key: 'IN_REVIEW', label: 'In review', count: counts.IN_REVIEW ?? 0 }, { key: 'WORK_QUEUE', label: 'Work queue', count: counts.WORK_QUEUE ?? 0 },
       { key: 'COMPLETED', label: 'Completed', count: counts.COMPLETED ?? 0 }, { key: 'REJECTED', label: 'Rejected', count: counts.REJECTED ?? 0 }]
    : [{ key: 'ALL', label: 'All', count: counts.ALL }, { key: 'MINE', label: 'Needs my action', count: counts.MINE },
       ...(counts.DRAFT ? [{ key: 'DRAFT', label: 'Drafts', count: counts.DRAFT }] : []), { key: 'SUBMITTED', label: 'Sent', count: counts.SUBMITTED ?? 0 },
       { key: 'IN_REVIEW', label: 'In review', count: counts.IN_REVIEW ?? 0 }, { key: 'ANSWERED', label: 'Answered', count: counts.ANSWERED ?? 0 }];

  const loading = (redlines.loading && !redlines.data) || (rfis.loading && !rfis.data);
  const error = redlines.error || rfis.error;
  const openCount = section === 'REDLINES' ? (counts.IN_REVIEW ?? 0) + (counts.WORK_QUEUE ?? 0) : (counts.SUBMITTED ?? 0) + (counts.IN_REVIEW ?? 0) + (counts.DRAFT ?? 0);

  const row = (x: R) => {
    const id = idOf(x);
    const on = current ? idOf(current) === id : false;
    const meta = section === 'REDLINES' ? redMeta(x.STATUS) : rfiMeta(x.STATUS);
    const mine = isMine(x);
    return (
      <Pressable key={id} onPress={() => open(id)} accessibilityRole="button" accessibilityState={{ selected: on }}
        style={({ hovered }: any) => ({ paddingHorizontal: space(4), paddingVertical: space(3), borderBottomWidth: 1, borderBottomColor: colors.border,
          backgroundColor: on ? colors.soft : hovered ? colors.surfaceAlt : '#fff', borderLeftWidth: 3, borderLeftColor: on ? colors.accent : 'transparent' })}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            {!siteId ? <Text style={{ fontSize: 12, fontWeight: '600', color: colors.accent }}>{x.SITE_ID}</Text> : null}
            {mine ? <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: colors.warn }} accessibilityLabel="Needs your action" /> : null}
          </View>
          <Badge text={meta.text} color={meta.color} />
        </View>
        <Text style={{ fontSize: 13.5, fontWeight: '600', color: colors.text, marginTop: 4 }} numberOfLines={2}>{section === 'REDLINES' ? x.MARKUP ?? '-' : x.SUBJECT ?? '-'}</Text>
        <Text style={{ fontSize: 12, color: colors.muted, marginTop: 2 }} numberOfLines={1}>
          {[section === 'REDLINES' ? `${x.DOC_TYPE} ${x.DOC_REVISION ?? ''} · sheet ${x.SHEET}` : (x.TO_PARTY === 'AE_ENGINEER' ? 'To A&E engineer' : 'To Admin'), ago(stamp(x))].filter(Boolean).join('  ·  ')}
        </Text>
      </Pressable>
    );
  };
  const detail = (x: R) => section === 'REDLINES'
    ? <RedlineDetail key={x.REDLINE_ID} x={x} reload={reload} showSite={!siteId} />
    : <RfiDetail key={x.RFI_ID} r={x} reload={reload} showSite={!siteId} />;

  return (
    <View style={{ gap: space(4) }}>
      <SegmentedTabs<Section> value={section} onChange={(v) => { setSection(v); setFilter('ALL'); setSel(null); }}
        tabs={[{ key: 'REDLINES', label: 'Redlines', icon: 'edit-3', count: redList.length }, { key: 'RFIS', label: 'RFIs', icon: 'help-circle', count: rfiAll.length }]} />

      <View style={{ flexDirection: 'row', gap: space(3), flexWrap: 'wrap' }}>
        <Stat label={section === 'REDLINES' ? 'Redlines' : 'RFIs'} value={counts.ALL} icon={section === 'REDLINES' ? 'edit-3' : 'help-circle'} />
        <Stat label="Open" value={openCount} icon="activity" color={openCount ? colors.warn : undefined} />
        <Stat label="Needs your action" value={counts.MINE} icon="check-square" color={counts.MINE ? colors.accent : undefined} onPress={() => setFilter('MINE')} />
        <Stat label={section === 'REDLINES' ? 'Completed' : 'Answered'} value={section === 'REDLINES' ? counts.COMPLETED ?? 0 : (counts.ANSWERED ?? 0)} icon="check-circle" color={colors.ok} />
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), padding: space(3), borderRadius: radius.lg, backgroundColor: tint.info.bg, borderWidth: 1, borderColor: tint.info.line }}>
        <Icon name="info" size={14} color={tint.info.fg} />
        <Text style={{ flex: 1, fontSize: 12.5, color: colors.text }}>{tip}</Text>
      </View>

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), flexWrap: 'wrap', zIndex: 5 }}>
        <SearchBox value={query} onChangeText={setQuery} placeholder={section === 'RFIS' ? 'Search subject, question or site' : 'Search markup, sheet or site'} style={{ flex: 1, minWidth: 240 }} />
        {section === 'RFIS' && role !== 'AE_ENGINEER' ? (
          <Select<'ALL' | 'ADMIN' | 'AE_ENGINEER'> value={recipient} width={190} onChange={(v) => { setRecipient(v); setFilter('ALL'); }}
            options={[{ key: 'ALL', label: 'All recipients' }, { key: 'ADMIN', label: 'To Admin' }, { key: 'AE_ENGINEER', label: 'To A&E engineer' }]} />
        ) : null}
        <Select<Sort> value={sort} width={170} onChange={setSort} options={[{ key: 'NEW', label: 'Newest first' }, { key: 'OLD', label: 'Oldest first' }, ...(siteId ? [] : [{ key: 'SITE' as Sort, label: 'By site' }])]} />
      </View>
      <Chips<string> value={filter} onChange={(v) => { setFilter(v); setSel(null); }} options={filterOptions} />

      {error ? <ErrorView error={error} onRetry={reload} /> : null}
      {loading ? <Loading rows={4} /> : null}
      {!loading && !visible.length ? (
        <Card><EmptyState icon={section === 'REDLINES' ? 'edit-3' : 'help-circle'}
          title={query ? 'Nothing matches your search' : filter === 'MINE' ? 'Nothing needs your action' : `No ${section === 'REDLINES' ? 'redlines' : 'RFIs'} here yet`}
          text={section === 'REDLINES' ? 'Redlines appear after a pipeline run finds a difference between the drawing and the drone survey.' : 'RFIs are raised from findings that need an answer from the A&E engineer or Admin.'} /></Card>
      ) : null}

      {!loading && visible.length ? (
        wide ? (
          <View style={{ flexDirection: 'row', gap: space(4), alignItems: 'flex-start' }}>
            <View style={[{ width: 380, backgroundColor: '#fff', borderRadius: radius.xl, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' }, shadow as any]}>{visible.map(row)}</View>
            <View style={{ flex: 1, minWidth: 0 }}>{current ? detail(current) : null}</View>
          </View>
        ) : (
          <>
            <View style={[{ backgroundColor: '#fff', borderRadius: radius.xl, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' }, shadow as any]}>{visible.map(row)}</View>
            <Dialog open={!!sel && !!current} onClose={() => setSel(null)} title={section === 'REDLINES' ? 'Redline' : 'RFI'} width={760}>
              <ScrollView style={{ maxHeight: 640 }} contentContainerStyle={{ padding: space(4) }}>{current ? detail(current) : null}</ScrollView>
            </Dialog>
          </>
        )
      ) : null}
    </View>
  );
}
