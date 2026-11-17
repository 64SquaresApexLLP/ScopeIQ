// Main sidebar tab: Redlines & RFIs
// Allows reviewing drawings, tracking markups, answering RFIs, and executing workflow actions across all sites.
import { router } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Linking, Pressable, RefreshControl, ScrollView, Text, TextInput, View, useWindowDimensions } from 'react-native';
import { ProofStrip } from '../../components/site/Redlines';
import { colors, font, radius, space, tint } from '../../components/theme';
import { Badge, Button, Card, Chips, EmptyState, ErrorView, Icon, IconBadge, KV, Loading, Muted, PageHeader, Row, s, SearchBox, Select, Tabs, Title } from '../../components/ui';
import { WorkflowActions } from '../../components/WorkflowActions';
import { api, ApiError, authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { label, when } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';

function RfiListItem({ r, reload }: { r: R; reload: () => void }) {
  const { user, can } = useAuth();
  const [answer, setAnswer] = useState(r.PROPOSED_ANSWER ?? '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);

  const sendAnswer = async () => {
    if (!answer.trim()) return;
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

  const displayStatus =
    r.STATUS === 'SUBMITTED' ? 'REQUEST' :
    r.STATUS === 'IN_REVIEW' ? 'IN REVIEW' :
    r.STATUS === 'ANSWERED' ? 'ANSWERED' :
    r.STATUS === 'CLOSED' ? 'CLOSED' :
    r.STATUS;

  const statusColor =
    r.STATUS === 'SUBMITTED' ? colors.info :
    r.STATUS === 'IN_REVIEW' ? colors.warn :
    r.STATUS === 'ANSWERED' || r.STATUS === 'CLOSED' ? colors.ok :
    colors.muted;

  const isTargetParty =
    r.TO_PARTY === 'AE_ENGINEER'
      ? user?.role === 'AE_ENGINEER'
      : can('ADMIN', 'ERICSSON');

  const canAnswer = r.STATUS === 'IN_REVIEW' && isTargetParty;

  return (
    <Card style={{ padding: space(4), gap: space(2) }}>
      <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <Row style={{ gap: space(2), alignItems: 'center' }}>
          <Pressable
            onPress={() => router.push({ pathname: '/site/[id]', params: { id: r.SITE_ID, tab: 'redlines' } })}
            style={({ pressed, hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: 4, opacity: pressed ? 0.7 : 1 })}
          >
            <Icon name="map-pin" size={13} color={colors.accent} />
            <Text style={{ color: colors.accent, fontWeight: '600', fontSize: 13 }}>{r.SITE_ID}</Text>
          </Pressable>
          <Badge text={r.TO_PARTY === 'AE_ENGINEER' ? 'To A&E Engineer' : 'To Admin'} color={colors.neutral} />
        </Row>
        <Badge text={displayStatus} color={statusColor} />
      </Row>

      <Text style={{ color: colors.text, fontWeight: '600', fontSize: 15, marginTop: space(1) }}>{r.SUBJECT}</Text>
      <Text style={{ color: colors.text, fontSize: 13.5, lineHeight: 20 }}>{r.QUESTION}</Text>

      {r.UPDATED_BY ? (
        <KV k="Submitted by" v={`${r.UPDATED_BY}${r.UPDATED_AT ? ` (${when(r.UPDATED_AT)})` : ''}`} />
      ) : null}
      {r.PROPOSED_ANSWER ? <KV k="Proposed answer" v={r.PROPOSED_ANSWER} /> : null}
      {r.ANSWER ? <KV k="Answer" v={r.ANSWER} /> : null}

      {/* Answer box for the designated target party */}
      {canAnswer ? (
        <View style={{ marginTop: space(2), padding: space(3), backgroundColor: colors.surfaceAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, gap: space(2) }}>
          <Text style={{ fontWeight: '600', fontSize: 13, color: colors.text }}>Respond to RFI</Text>
          <TextInput
            style={[s.input, { minHeight: 65, backgroundColor: colors.card }]}
            multiline
            placeholder="Type answer here..."
            value={answer}
            onChangeText={setAnswer}
          />
          <Row style={{ justifyContent: 'flex-end' }}>
            <Button small title="Send answer" disabled={!answer.trim() || busy} onPress={sendAnswer} />
          </Row>
          {err ? <ErrorView error={err} /> : null}
        </View>
      ) : r.STATUS === 'IN_REVIEW' ? (
        <View style={{ marginTop: space(2), padding: space(3), backgroundColor: tint.info.bg, borderRadius: radius.md, flexDirection: 'row', gap: 8, alignItems: 'center' }}>
          <Icon name="clock" size={14} color={tint.info.fg} />
          <Text style={{ fontSize: 12.5, color: tint.info.fg }}>Awaiting a response from {r.TO_PARTY === 'AE_ENGINEER' ? 'the A&E Engineer' : 'the Admin'}.</Text>
        </View>
      ) : null}

      <View style={{ marginTop: space(1) }}>
        <WorkflowActions
          actions={(r.ACTIONS ?? []).filter((a: string) => a !== 'ANSWER')}
          endpoint={`/rfis/${r.RFI_ID}/transition`}
          entity="RFI"
          onDone={reload}
        />
      </View>
    </Card>
  );
}

function RedlineListItem({ x, reload }: { x: R; reload: () => void }) {
  const { user } = useAuth();
  const displayStatus =
    ['IN_REVIEW', 'APPROVED', 'SENT_TO_AE', 'DRAFT'].includes(x.STATUS) ? 'IN_REVIEW' :
    ['WORK_QUEUE', 'ACKNOWLEDGED'].includes(x.STATUS) ? 'WORK_QUEUE' :
    ['COMPLETED', 'INCORPORATED', 'CLOSED'].includes(x.STATUS) ? 'COMPLETED' :
    x.STATUS;

  const statusCol =
    displayStatus === 'IN_REVIEW' ? colors.warn :
    displayStatus === 'WORK_QUEUE' ? colors.info :
    displayStatus === 'COMPLETED' ? colors.ok :
    displayStatus === 'REJECTED' ? colors.danger : colors.muted;

  const formatRole = (role?: string) => {
    if (!role) return '';
    if (role === 'ADMIN') return 'Admin';
    if (role === 'AE_ENGINEER') return 'A&E Engineer';
    if (role === 'SCOPER') return 'Scoper';
    if (role === 'REVIEWER') return 'Reviewer';
    return role.replace(/_/g, ' ');
  };

  return (
    <Card style={{ padding: space(4), gap: space(2) }}>
      <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <Row style={{ gap: space(2), alignItems: 'center', flexWrap: 'wrap', flex: 1 }}>
          <Pressable
            onPress={() => router.push({ pathname: '/site/[id]', params: { id: x.SITE_ID, tab: 'redlines' } })}
            style={({ pressed }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: 4, opacity: pressed ? 0.7 : 1 })}
          >
            <Icon name="map-pin" size={13} color={colors.accent} />
            <Text style={{ color: colors.accent, fontWeight: '600', fontSize: 13 }}>{x.SITE_ID}</Text>
          </Pressable>
          <Title>{`${x.DOC_TYPE} ${x.DOC_REVISION ?? ''} · sheet ${x.SHEET}`}</Title>

          {/* Attribution badge: indicates who responded, or if it is pending for Admin & A&E */}
          {x.LAST_RESPONSE ? (
            <Badge
              text={`Responded by ${formatRole(x.LAST_RESPONSE.ACTOR_ROLE)} (${x.LAST_RESPONSE.ACTOR_USER_ID})`}
              color={colors.neutral}
            />
          ) : (
            <Badge text="For Admin and A&E" color={colors.neutral} />
          )}
        </Row>
        <Badge text={displayStatus.replace('_', ' ')} color={statusCol} />
      </Row>

      <Text style={{ color: colors.text, fontWeight: '600', fontSize: 14.5, marginTop: space(1) }}>{x.MARKUP}</Text>
      <View style={{ flexDirection: 'row', gap: space(3), flexWrap: 'wrap', marginTop: space(1) }}>
        <View style={{ flex: 1, minWidth: 200, padding: space(3), borderRadius: radius.md, backgroundColor: tint.danger.bg, borderWidth: 1, borderColor: tint.danger.line }}>
          <Text style={{ fontSize: 11.5, fontWeight: '600', color: tint.danger.fg }}>DRAWING SHOWS</Text>
          <Text style={{ fontSize: 13.5, color: colors.text, marginTop: 4 }}>{x.CHANGE_FROM || '-'}</Text>
        </View>
        <View style={{ flex: 1, minWidth: 200, padding: space(3), borderRadius: radius.md, backgroundColor: tint.ok.bg, borderWidth: 1, borderColor: tint.ok.line }}>
          <Text style={{ fontSize: 11.5, fontWeight: '600', color: tint.ok.fg }}>FIELD (DRONE) SHOWS</Text>
          <Text style={{ fontSize: 13.5, color: colors.text, marginTop: 4 }}>{x.CHANGE_TO || '-'}</Text>
        </View>
      </View>
      {Array.isArray(x.PROOF) && x.PROOF.length ? <ProofStrip proof={x.PROOF} /> : null}

      <KV
        k="Submitted by"
        v={`${x.SUBMITTED_BY || 'scoper'}${x.SUBMITTED_AT ? ` (${when(x.SUBMITTED_AT)})` : ''}`}
      />

      {x.REVIEWED_BY ? (
        <KV
          k="Reviewed by"
          v={`${x.REVIEWED_BY} (${formatRole(x.REVIEWED_ROLE)})${x.REVIEWED_AT ? ` (${when(x.REVIEWED_AT)})` : ''}`}
        />
      ) : null}

      {x.COMPLETED_BY ? (
        <KV
          k="Completed by"
          v={`${x.COMPLETED_BY} (${formatRole(x.COMPLETED_ROLE)})${x.COMPLETED_AT ? ` (${when(x.COMPLETED_AT)})` : ''}`}
        />
      ) : null}

      {x.REJECTED_BY ? (
        <KV
          k="Rejected by"
          v={`${x.REJECTED_BY} (${formatRole(x.REJECTED_ROLE)})${x.REJECTED_AT ? ` (${when(x.REJECTED_AT)})` : ''}`}
        />
      ) : null}

      {/* Response callout banner highlighting the latest action taken, actor role & note */}
      {x.LAST_RESPONSE ? (
        <View
          style={{
            marginTop: space(2),
            padding: space(2.5),
            backgroundColor: colors.surfaceAlt,
            borderRadius: radius.md,
            borderLeftWidth: 3,
            borderLeftColor: colors.accent,
            gap: 4,
          }}
        >
          <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
            <Text style={{ fontWeight: '700', fontSize: 12.5, color: colors.text }}>
              Response from {formatRole(x.LAST_RESPONSE.ACTOR_ROLE)} ({x.LAST_RESPONSE.ACTOR_USER_ID})
            </Text>
            <Text style={{ fontSize: 11.5, color: colors.muted }}>
              {when(x.LAST_RESPONSE.EVENT_TS)}
            </Text>
          </Row>
          <Text style={{ fontSize: 12, color: colors.text }}>
            Action: <Text style={{ fontWeight: '700' }}>{x.LAST_RESPONSE.ACTION.replace('_', ' ')}</Text>
            {`  ·  Status: `}<Text style={{ fontWeight: '700', color: statusCol }}>{displayStatus.replace('_', ' ')}</Text>
          </Text>
          {x.LAST_RESPONSE.REASON_CODE ? (
            <Text style={{ fontSize: 12, color: colors.danger, fontWeight: '600' }}>
              Reason: {x.LAST_RESPONSE.REASON_CODE}
            </Text>
          ) : null}
          {x.LAST_RESPONSE.COMMENT ? (
            <Text style={{ fontSize: 12, color: colors.text, fontStyle: 'italic', marginTop: 2 }}>
              "{x.LAST_RESPONSE.COMMENT}"
            </Text>
          ) : null}
        </View>
      ) : null}

      <Row style={{ marginTop: space(1), gap: space(2), flexWrap: 'wrap' }}>
        {x.PDF_URL ? (
          <Button
            small
            kind="secondary"
            icon="file-text"
            title="Open redlined CD (PDF)"
            onPress={() => Linking.openURL(authedUrl(x.PDF_URL))}
          />
        ) : null}
        {displayStatus === 'WORK_QUEUE' && ['AE_ENGINEER', 'ADMIN'].includes(user?.role ?? '') ? (
          <Button
            small
            kind="secondary"
            title="View in Work queue"
            onPress={() => router.push('/(tabs)/queue')}
          />
        ) : null}
      </Row>

      {['AE_ENGINEER', 'ADMIN'].includes(user?.role ?? '') && (x.ACTIONS ?? []).length ? (
        <View style={{ marginTop: space(1) }}>
          <WorkflowActions
            actions={x.ACTIONS ?? []}
            endpoint={`/redlines/${x.REDLINE_ID}/transition`}
            entity="REDLINE"
            onDone={reload}
          />
        </View>
      ) : null}
    </Card>
  );
}

type RfiScope = 'ALL' | 'ADMIN' | 'SENT_TO_AE';
type RfiFilter = 'ALL' | 'IN_REVIEW' | 'REQUEST' | 'ANSWERED';
type RedFilter = 'ALL' | 'IN_REVIEW' | 'WORK_QUEUE' | 'COMPLETED' | 'REJECTED';

export default function RfisScreen() {
  const { user, can } = useAuth();
  const isAe = user?.role === 'AE_ENGINEER';
  const allowed = can('ADMIN', 'AE_ENGINEER', 'SCOPER', 'REVIEWER', 'ERICSSON');
  const rfis = useApi<R[]>(allowed ? '/rfis' : null);
  const redlines = useApi<R[]>(allowed ? '/redlines' : null);

  const [section, setSection] = useState<'RFIS' | 'REDLINES'>('REDLINES');
  const [rfiScope, setRfiScope] = useState<RfiScope>('ALL');
  const [rfiFilter, setRfiFilter] = useState<RfiFilter>('ALL');
  const [redFilter, setRedFilter] = useState<RedFilter>('ALL');
  const [query, setQuery] = useState('');
  const [selRfi, setSelRfi] = useState<string | null>(null);
  const [selRed, setSelRed] = useState<string | null>(null);
  const { width } = useWindowDimensions();

  if (!allowed) {
    return (
      <View style={[s.screen, { alignItems: 'center', justifyContent: 'center', padding: space(8) }]}>
        <IconBadge name="lock" color={colors.muted} size={56} />
        <Text style={{ fontWeight: '800', fontSize: 18, color: colors.text, marginTop: space(3) }}>Restricted access</Text>
        <Muted>Only authorized scoping, engineering, and admin team members can access the Redlines & RFIs tab.</Muted>
        <View style={{ marginTop: space(4) }}>
          <Button title="Go to Dashboard" onPress={() => router.replace('/(tabs)')} />
        </View>
      </View>
    );
  }

  const rfiList = useMemo(() => (rfis.data ?? []).filter((x) => x.STATUS !== 'DRAFT'), [rfis.data]);
  const redList = redlines.data ?? [];

  // Recipient scope counts (All RFIs vs For Admin vs Sent to A&E)
  const scopeCounts = useMemo(() => {
    const total = rfiList.length;
    const adminCount = rfiList.filter((x) => x.TO_PARTY !== 'AE_ENGINEER').length;
    const aeCount = rfiList.filter((x) => x.TO_PARTY === 'AE_ENGINEER').length;
    return {
      ALL: total,
      ADMIN: adminCount,
      SENT_TO_AE: aeCount,
    };
  }, [rfiList]);

  // Scoped list of RFIs based on Admin's selected workstream (or locked to A&E for A&E Engineer)
  const scopedRfis = useMemo(() => {
    if (isAe) {
      return rfiList.filter((x) => x.TO_PARTY === 'AE_ENGINEER');
    }
    if (rfiScope === 'ADMIN') {
      return rfiList.filter((x) => x.TO_PARTY !== 'AE_ENGINEER');
    }
    if (rfiScope === 'SENT_TO_AE') {
      return rfiList.filter((x) => x.TO_PARTY === 'AE_ENGINEER');
    }
    return rfiList;
  }, [rfiList, rfiScope, isAe]);

  // Status counts strictly for the currently scoped RFIs:
  // All = In Review + Request + Answered (always mathematically exact)
  const rfiCounts = useMemo(() => {
    const request = scopedRfis.filter((x) => x.STATUS === 'SUBMITTED').length;
    const inReview = scopedRfis.filter((x) => x.STATUS === 'IN_REVIEW').length;
    const answered = scopedRfis.filter((x) => x.STATUS === 'ANSWERED' || x.STATUS === 'CLOSED').length;
    return {
      ALL: scopedRfis.length,
      IN_REVIEW: inReview,
      REQUEST: request,
      ANSWERED: answered,
    };
  }, [scopedRfis]);

  const redCounts = useMemo(() => ({
    ALL: redList.length,
    IN_REVIEW: redList.filter((x) => ['IN_REVIEW', 'APPROVED', 'SENT_TO_AE', 'DRAFT'].includes(x.STATUS)).length,
    WORK_QUEUE: redList.filter((x) => ['WORK_QUEUE', 'ACKNOWLEDGED'].includes(x.STATUS)).length,
    COMPLETED: redList.filter((x) => ['COMPLETED', 'INCORPORATED', 'CLOSED'].includes(x.STATUS)).length,
    REJECTED: redList.filter((x) => x.STATUS === 'REJECTED').length,
  }), [redList]);

  const filteredRfis = useMemo(() => {
    let list = scopedRfis;
    if (rfiFilter === 'REQUEST') {
      list = list.filter((x) => x.STATUS === 'SUBMITTED');
    } else if (rfiFilter === 'IN_REVIEW') {
      list = list.filter((x) => x.STATUS === 'IN_REVIEW');
    } else if (rfiFilter === 'ANSWERED') {
      list = list.filter((x) => x.STATUS === 'ANSWERED' || x.STATUS === 'CLOSED');
    }
    const q = query.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (x) =>
          x.SITE_ID?.toLowerCase().includes(q) ||
          x.SUBJECT?.toLowerCase().includes(q) ||
          x.QUESTION?.toLowerCase().includes(q) ||
          x.TO_PARTY?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [scopedRfis, rfiFilter, query]);

  const filteredRedlines = useMemo(() => {
    let list = redList;
    if (redFilter === 'IN_REVIEW') {
      list = list.filter((x) => ['IN_REVIEW', 'APPROVED', 'SENT_TO_AE', 'DRAFT'].includes(x.STATUS));
    } else if (redFilter === 'WORK_QUEUE') {
      list = list.filter((x) => ['WORK_QUEUE', 'ACKNOWLEDGED'].includes(x.STATUS));
    } else if (redFilter === 'COMPLETED') {
      list = list.filter((x) => ['COMPLETED', 'INCORPORATED', 'CLOSED'].includes(x.STATUS));
    } else if (redFilter === 'REJECTED') {
      list = list.filter((x) => x.STATUS === 'REJECTED');
    }
    const q = query.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (x) =>
          x.SITE_ID?.toLowerCase().includes(q) ||
          x.MARKUP?.toLowerCase().includes(q) ||
          x.SHEET?.toLowerCase().includes(q) ||
          x.DOC_TYPE?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [redList, redFilter, query]);

  const reloadAll = () => {
    rfis.reload();
    redlines.reload();
  };

  const loading = (rfis.loading && !rfis.data) || (redlines.loading && !redlines.data);
  const error = rfis.error || redlines.error;
  const wide = width >= 1100;
  const curRfi = filteredRfis.find((x) => x.RFI_ID === selRfi) ?? filteredRfis[0];
  const curRed = filteredRedlines.find((x) => x.REDLINE_ID === selRed) ?? filteredRedlines[0];

  const listRow = (key: string, on: boolean, onPress: () => void, site: string, title: string, sub: string, badge: React.ReactNode) => (
    <Pressable key={key} onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: on }}
      style={({ hovered }: any) => ({ paddingHorizontal: space(4), paddingVertical: space(3), borderBottomWidth: 1, borderBottomColor: colors.border,
        backgroundColor: on ? colors.soft : hovered ? colors.surfaceAlt : '#fff', borderLeftWidth: 3, borderLeftColor: on ? colors.accent : 'transparent' })}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <Text style={{ fontSize: 12, fontWeight: '600', color: colors.accent }}>{site}</Text>
        {badge}
      </View>
      <Text style={{ fontSize: 13.5, fontWeight: '600', color: colors.text, marginTop: 4 }} numberOfLines={2}>{title}</Text>
      <Text style={{ fontSize: 12, color: colors.muted, marginTop: 2 }} numberOfLines={1}>{sub}</Text>
    </Pressable>
  );
  const rfiStatus = (st: string) => st === 'SUBMITTED' ? { t: 'Request', c: colors.info } : st === 'IN_REVIEW' ? { t: 'In review', c: colors.warn } : st === 'ANSWERED' || st === 'CLOSED' ? { t: label(st), c: colors.ok } : { t: label(st), c: colors.neutral };
  const redStatus = (st: string) => ['IN_REVIEW', 'APPROVED', 'SENT_TO_AE', 'DRAFT'].includes(st) ? { t: 'In review', c: colors.warn } : ['WORK_QUEUE', 'ACKNOWLEDGED'].includes(st) ? { t: 'Work queue', c: colors.info } : ['COMPLETED', 'INCORPORATED', 'CLOSED'].includes(st) ? { t: 'Completed', c: colors.ok } : st === 'REJECTED' ? { t: 'Rejected', c: colors.danger } : { t: label(st), c: colors.neutral };
  const emptyText = (what: string, f: string) => query ? `No ${what} match your search.` : f === 'ALL' ? `No ${what} yet.` : `No ${what} with this status.`;

  return (
    <ScrollView
      style={s.screen}
      contentContainerStyle={[s.content, { maxWidth: 1440, width: '100%', alignSelf: 'center' }]}
      refreshControl={<RefreshControl refreshing={rfis.loading || redlines.loading} onRefresh={reloadAll} />}
    >
      <PageHeader title="Redlines & RFIs" subtitle="Review drawing corrections with their drone evidence, and answer requests for information across sites." />

      <Tabs<'RFIS' | 'REDLINES'> value={section} onChange={setSection} style={{ marginBottom: space(4) }}
        tabs={[{ key: 'REDLINES', label: 'Redlines', icon: 'edit-3', count: redCounts.ALL }, { key: 'RFIS', label: 'RFIs', icon: 'help-circle', count: isAe ? scopeCounts.SENT_TO_AE : scopeCounts.ALL }]} />

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), flexWrap: 'wrap', marginBottom: space(3), zIndex: 5 }}>
        <SearchBox value={query} onChangeText={setQuery} placeholder={section === 'RFIS' ? 'Search site, subject or question' : 'Search site, sheet or markup'} style={{ flex: 1, minWidth: 260 }} />
        {section === 'RFIS' && !isAe ? (
          <Select<RfiScope> value={rfiScope} width={220} onChange={(v) => { setRfiScope(v); setRfiFilter('ALL'); }}
            options={[{ key: 'ALL', label: `All recipients (${scopeCounts.ALL})` }, { key: 'ADMIN', label: `To Admin (${scopeCounts.ADMIN})` }, { key: 'SENT_TO_AE', label: `To A&E Engineer (${scopeCounts.SENT_TO_AE})` }]} />
        ) : null}
      </View>
      <View style={{ marginBottom: space(4) }}>
        {section === 'RFIS' ? (
          <Chips<RfiFilter> value={rfiFilter} onChange={setRfiFilter} options={[
            { key: 'ALL', label: 'All', count: rfiCounts.ALL }, { key: 'REQUEST', label: 'Request', count: rfiCounts.REQUEST },
            { key: 'IN_REVIEW', label: 'In review', count: rfiCounts.IN_REVIEW }, { key: 'ANSWERED', label: 'Answered', count: rfiCounts.ANSWERED }]} />
        ) : (
          <Chips<RedFilter> value={redFilter} onChange={setRedFilter} options={[
            { key: 'ALL', label: 'All', count: redCounts.ALL }, { key: 'IN_REVIEW', label: 'In review', count: redCounts.IN_REVIEW },
            { key: 'WORK_QUEUE', label: 'Work queue', count: redCounts.WORK_QUEUE }, { key: 'COMPLETED', label: 'Completed', count: redCounts.COMPLETED },
            { key: 'REJECTED', label: 'Rejected', count: redCounts.REJECTED }]} />
        )}
      </View>

      {error ? <ErrorView error={error} onRetry={reloadAll} /> : null}
      {loading ? <Loading rows={5} /> : null}

      {!loading && section === 'RFIS' && !filteredRfis.length ? <Card><EmptyState icon="help-circle" title={emptyText('RFIs', rfiFilter)} text="RFIs are raised from findings that need an answer from the A&E Engineer or the Admin." /></Card> : null}
      {!loading && section === 'REDLINES' && !filteredRedlines.length ? <Card><EmptyState icon="edit-3" title={emptyText('redlines', redFilter)} text="Redlines appear after a pipeline run finds a difference between the drawing and the drone survey." /></Card> : null}

      {wide && !loading ? (
        <View style={{ flexDirection: 'row', gap: space(4), alignItems: 'flex-start' }}>
          {(section === 'RFIS' ? filteredRfis.length : filteredRedlines.length) ? (
            <View style={[s.card, { width: 360, padding: 0, overflow: 'hidden' }]}>
              <View style={{ paddingHorizontal: space(4), paddingVertical: space(2.5), backgroundColor: colors.surfaceAlt, borderBottomWidth: 1, borderBottomColor: colors.border }}>
                <Text style={s.thText}>{section === 'RFIS' ? `${filteredRfis.length} RFI${filteredRfis.length === 1 ? '' : 's'}` : `${filteredRedlines.length} redline${filteredRedlines.length === 1 ? '' : 's'}`}</Text>
              </View>
              {section === 'RFIS'
                ? filteredRfis.map((r) => { const b = rfiStatus(r.STATUS); return listRow(r.RFI_ID, r === curRfi, () => setSelRfi(r.RFI_ID), r.SITE_ID, r.SUBJECT ?? '-', r.TO_PARTY === 'AE_ENGINEER' ? 'To A&E Engineer' : 'To Admin', <Badge text={b.t} color={b.c} />); })
                : filteredRedlines.map((x) => { const b = redStatus(x.STATUS); return listRow(x.REDLINE_ID, x === curRed, () => setSelRed(x.REDLINE_ID), x.SITE_ID, x.MARKUP ?? '-', `${x.DOC_TYPE} ${x.DOC_REVISION ?? ''} · sheet ${x.SHEET}`, <Badge text={b.t} color={b.c} />); })}
            </View>
          ) : null}
          <View style={{ flex: 1, minWidth: 0 }}>
            {section === 'RFIS'
              ? curRfi ? <RfiListItem key={curRfi.RFI_ID} r={curRfi} reload={rfis.reload} /> : null
              : curRed ? <RedlineListItem key={curRed.REDLINE_ID} x={curRed} reload={redlines.reload} /> : null}
          </View>
        </View>
      ) : !loading ? (
        section === 'RFIS'
          ? filteredRfis.map((r) => <RfiListItem key={r.RFI_ID} r={r} reload={rfis.reload} />)
          : filteredRedlines.map((x) => <RedlineListItem key={x.REDLINE_ID} x={x} reload={redlines.reload} />)
      ) : null}
    </ScrollView>
  );
}
