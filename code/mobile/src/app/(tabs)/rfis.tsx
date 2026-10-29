// Main sidebar tab: Redlines & RFIs
// Allows reviewing drawings, tracking markups, answering RFIs, and executing workflow actions across all sites.
import { router } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Linking, Pressable, RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';
import { colors, space } from '../../components/theme';
import { Badge, Button, Card, Chips, Empty, ErrorView, Hero, IconBadge, KV, Loading, Muted, Row, s, Title } from '../../components/ui';
import { WorkflowActions } from '../../components/WorkflowActions';
import { api, ApiError, authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { when } from '../../lib/format';
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
    r.STATUS === 'SUBMITTED' ? 'IN REVIEW' :
    r.STATUS === 'ANSWERED' ? 'ANSWERED' :
    r.STATUS === 'CLOSED' ? 'CLOSED' :
    r.STATUS;

  const statusColor =
    r.STATUS === 'SUBMITTED' ? colors.warn :
    r.STATUS === 'ANSWERED' || r.STATUS === 'CLOSED' ? colors.ok :
    colors.muted;

  const canAnswer =
    (r.STATUS === 'SUBMITTED' || (r.ACTIONS ?? []).includes('ANSWER')) &&
    (can('ADMIN', 'ERICSSON') || (user?.role === 'AE_ENGINEER' && r.TO_PARTY === 'AE_ENGINEER'));

  return (
    <Card style={{ padding: space(4), gap: space(2) }}>
      <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <Row style={{ gap: space(2), alignItems: 'center' }}>
          <Pressable
            onPress={() => router.push({ pathname: '/site/[id]', params: { id: r.SITE_ID, tab: 'redlines' } })}
            style={({ pressed }) => ({
              backgroundColor: colors.primary + '18',
              paddingHorizontal: 8,
              paddingVertical: 4,
              borderRadius: 6,
              opacity: pressed ? 0.7 : 1,
            })}
          >
            <Text style={{ color: colors.primary, fontWeight: '700', fontSize: 13 }}>{r.SITE_ID}</Text>
          </Pressable>
          <Badge
            text={r.TO_PARTY === 'AE_ENGINEER' ? 'To AE_ENGINEER' : 'To Admin'}
            color={r.TO_PARTY === 'AE_ENGINEER' ? colors.accent : colors.primary}
          />
        </Row>
        <Badge text={displayStatus} color={statusColor} />
      </Row>

      <Text style={{ color: colors.text, fontWeight: '700', fontSize: 14 }}>{r.SUBJECT}</Text>
      <Muted style={{ color: colors.text }}>{r.QUESTION}</Muted>

      {r.UPDATED_BY ? (
        <KV k="Submitted by" v={`${r.UPDATED_BY}${r.UPDATED_AT ? ` (${when(r.UPDATED_AT)})` : ''}`} />
      ) : null}
      {r.PROPOSED_ANSWER ? <KV k="Proposed answer" v={r.PROPOSED_ANSWER} /> : null}
      {r.ANSWER ? <KV k="Answer" v={r.ANSWER} /> : null}

      {/* Answer box for A&E Engineer / Ericsson / Admin */}
      {canAnswer ? (
        <View style={{ marginTop: space(2), padding: space(3), backgroundColor: colors.bg, borderRadius: 8, gap: space(2) }}>
          <Text style={{ fontWeight: '700', fontSize: 13, color: colors.text }}>Respond to RFI</Text>
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
    displayStatus === 'WORK_QUEUE' ? colors.primary :
    displayStatus === 'COMPLETED' ? colors.ok :
    displayStatus === 'REJECTED' ? colors.danger : colors.muted;

  return (
    <Card style={{ padding: space(4), gap: space(2) }}>
      <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <Row style={{ gap: space(2), alignItems: 'center' }}>
          <Pressable
            onPress={() => router.push({ pathname: '/site/[id]', params: { id: x.SITE_ID, tab: 'redlines' } })}
            style={({ pressed }) => ({
              backgroundColor: colors.primary + '18',
              paddingHorizontal: 8,
              paddingVertical: 4,
              borderRadius: 6,
              opacity: pressed ? 0.7 : 1,
            })}
          >
            <Text style={{ color: colors.primary, fontWeight: '700', fontSize: 13 }}>{x.SITE_ID}</Text>
          </Pressable>
          <Title>{`${x.DOC_TYPE} ${x.DOC_REVISION ?? ''} sheet ${x.SHEET}`}</Title>
        </Row>
        <Badge text={displayStatus.replace('_', ' ')} color={statusCol} />
      </Row>

      <Text style={{ color: colors.text, fontWeight: '600', fontSize: 13.5 }}>{x.MARKUP}</Text>
      <KV k="Was" v={x.CHANGE_FROM} />
      <KV k="Now" v={x.CHANGE_TO} />
      {x.UPDATED_BY ? (
        <KV k="Submitted by" v={`${x.UPDATED_BY}${x.UPDATED_AT ? ` (${when(x.UPDATED_AT)})` : ''}`} />
      ) : null}

      <Row style={{ marginTop: space(1), gap: space(2), flexWrap: 'wrap' }}>
        {x.PDF_URL ? (
          <Button
            small
            kind="secondary"
            title="Open red-marked CD (PDF)"
            onPress={() => Linking.openURL(authedUrl(x.PDF_URL))}
          />
        ) : null}
        {displayStatus === 'WORK_QUEUE' && user?.role === 'AE_ENGINEER' ? (
          <Button
            small
            kind="secondary"
            title="View in Work queue"
            onPress={() => router.push('/(tabs)/queue')}
          />
        ) : null}
      </Row>

      {user?.role === 'AE_ENGINEER' && (x.ACTIONS ?? []).length ? (
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

type RfiFilter = 'ALL' | 'IN_REVIEW' | 'REQUEST' | 'ANSWERED' | 'SENT_TO_AE';
type RedFilter = 'ALL' | 'IN_REVIEW' | 'WORK_QUEUE' | 'COMPLETED' | 'REJECTED';

export default function RfisScreen() {
  const { user, can } = useAuth();
  const isAe = user?.role === 'AE_ENGINEER';
  const allowed = can('ADMIN', 'AE_ENGINEER', 'SCOPER', 'REVIEWER', 'ERICSSON');
  const rfis = useApi<R[]>(allowed ? '/rfis' : null);
  const redlines = useApi<R[]>(allowed ? '/redlines' : null);

  const [section, setSection] = useState<'RFIS' | 'REDLINES'>('RFIS');
  const [rfiFilter, setRfiFilter] = useState<RfiFilter>('ALL');
  const [redFilter, setRedFilter] = useState<RedFilter>('ALL');
  const [query, setQuery] = useState('');

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

  const rfiCounts = useMemo(() => {
    const inReview = rfiList.filter((x) => x.STATUS === 'SUBMITTED' || x.STATUS === 'IN_REVIEW').length;
    const request = rfiList.filter((x) => x.TO_PARTY === 'ADMIN').length;
    const answered = rfiList.filter((x) => x.STATUS === 'ANSWERED' || x.STATUS === 'CLOSED').length;
    const sentToAe = rfiList.filter((x) => x.TO_PARTY === 'AE_ENGINEER').length;
    return {
      DISTINCT: rfiList.length,
      ALL: inReview + request + answered + sentToAe,
      IN_REVIEW: inReview,
      REQUEST: request,
      ANSWERED: answered,
      SENT_TO_AE: sentToAe,
    };
  }, [rfiList]);

  const redCounts = useMemo(() => ({
    ALL: redList.length,
    IN_REVIEW: redList.filter((x) => ['IN_REVIEW', 'APPROVED', 'SENT_TO_AE', 'DRAFT'].includes(x.STATUS)).length,
    WORK_QUEUE: redList.filter((x) => ['WORK_QUEUE', 'ACKNOWLEDGED'].includes(x.STATUS)).length,
    COMPLETED: redList.filter((x) => ['COMPLETED', 'INCORPORATED', 'CLOSED'].includes(x.STATUS)).length,
    REJECTED: redList.filter((x) => x.STATUS === 'REJECTED').length,
  }), [redList]);

  const filteredRfis = useMemo(() => {
    let list = rfiList;
    if (rfiFilter === 'IN_REVIEW') {
      list = list.filter((x) => x.STATUS === 'SUBMITTED' || x.STATUS === 'IN_REVIEW');
    } else if (rfiFilter === 'REQUEST') {
      list = list.filter((x) => x.TO_PARTY === 'ADMIN');
    } else if (rfiFilter === 'ANSWERED') {
      list = list.filter((x) => x.STATUS === 'ANSWERED' || x.STATUS === 'CLOSED');
    } else if (rfiFilter === 'SENT_TO_AE') {
      list = list.filter((x) => x.TO_PARTY === 'AE_ENGINEER');
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
  }, [rfiList, rfiFilter, query]);

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

  return (
    <ScrollView
      style={s.screen}
      contentContainerStyle={[s.content, { maxWidth: 860, width: '100%', alignSelf: 'center' }]}
      refreshControl={<RefreshControl refreshing={rfis.loading || redlines.loading} onRefresh={reloadAll} />}
    >
      <Hero
        icon="edit-3"
        title="Redlines & RFIs"
        subtitle="Review drawing redlines, acknowledge markups, and answer Requests for Information across sites."
      />

      {/* Primary Section Switcher */}
      <Chips<'RFIS' | 'REDLINES'>
        value={section}
        onChange={setSection}
        options={[
          { key: 'RFIS', label: `RFIs (${rfiCounts.DISTINCT})` },
          { key: 'REDLINES', label: `Redlines (${redCounts.ALL})` },
        ]}
      />

      {/* Sub filters and search */}
      <Row style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
        {section === 'RFIS' ? (
          <Chips<RfiFilter>
            value={rfiFilter}
            onChange={setRfiFilter}
            options={[
              { key: 'ALL', label: `All (${rfiCounts.ALL})` },
              { key: 'IN_REVIEW', label: `In Review (${rfiCounts.IN_REVIEW})` },
              { key: 'REQUEST', label: `Request (${rfiCounts.REQUEST})` },
              { key: 'ANSWERED', label: `Answered (${rfiCounts.ANSWERED})` },
              { key: 'SENT_TO_AE', label: `Sent to A&E (${rfiCounts.SENT_TO_AE})` },
            ]}
          />
        ) : (
          <Chips<RedFilter>
            value={redFilter}
            onChange={setRedFilter}
            options={[
              { key: 'ALL', label: `All (${redCounts.ALL})` },
              { key: 'IN_REVIEW', label: `In Review (${redCounts.IN_REVIEW})` },
              { key: 'WORK_QUEUE', label: `Work Queue (${redCounts.WORK_QUEUE})` },
              { key: 'COMPLETED', label: `Completed (${redCounts.COMPLETED})` },
              { key: 'REJECTED', label: `Rejected (${redCounts.REJECTED})` },
            ]}
          />
        )}
        <TextInput
          style={[s.input, { minWidth: 200, maxWidth: 300 }]}
          placeholder="Search site, sheet, subject..."
          value={query}
          onChangeText={setQuery}
        />
      </Row>

      {error ? <ErrorView error={error} onRetry={reloadAll} /> : null}
      {loading ? <Loading /> : null}

      {section === 'RFIS' ? (
        <>
          {!loading && !filteredRfis.length ? (
            <Empty text={query ? 'No RFIs match your search.' : `No ${rfiFilter === 'ALL' ? '' : rfiFilter.replace('_', ' ').toLowerCase() + ' '}RFIs found.`} />
          ) : null}
          {filteredRfis.map((r) => (
            <RfiListItem key={r.RFI_ID} r={r} reload={rfis.reload} />
          ))}
        </>
      ) : (
        <>
          {!loading && !filteredRedlines.length ? (
            <Empty text={query ? 'No redlines match your search.' : `No ${redFilter === 'ALL' ? '' : redFilter.replace('_', ' ').toLowerCase() + ' '}redlines found.`} />
          ) : null}
          {filteredRedlines.map((x) => (
            <RedlineListItem key={x.REDLINE_ID} x={x} reload={redlines.reload} />
          ))}
        </>
      )}
    </ScrollView>
  );
}
