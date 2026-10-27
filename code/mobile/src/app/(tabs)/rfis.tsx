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
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';

function RfiListItem({ r, reload }: { r: R; reload: () => void }) {
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

  const statusColor =
    r.STATUS === 'SUBMITTED' ? colors.warn :
    r.STATUS === 'ANSWERED' || r.STATUS === 'CLOSED' ? colors.ok :
    colors.muted;

  const canAnswer = r.STATUS === 'SUBMITTED' || (r.ACTIONS ?? []).includes('ANSWER');

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
        </Row>
        <Badge text={r.STATUS} color={statusColor} />
      </Row>

      <Text style={{ color: colors.text, fontWeight: '700', fontSize: 14 }}>{r.SUBJECT}</Text>
      <Muted style={{ color: colors.text }}>{r.QUESTION}</Muted>

      {r.PROPOSED_ANSWER ? <KV k="Proposed answer" v={r.PROPOSED_ANSWER} /> : null}
      {r.ANSWER ? <KV k="Answer" v={r.ANSWER} /> : null}

      {/* Answer box for A&E Engineer / Admin */}
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
        {/* Recipients (A&E / Admin) answer via the box above and close after answering. Filter out SUBMIT (for Scopers). */}
        <WorkflowActions
          actions={(r.ACTIONS ?? []).filter((a: string) => a !== 'ANSWER' && a !== 'SUBMIT')}
          endpoint={`/rfis/${r.RFI_ID}/transition`}
          entity="RFI"
          onDone={reload}
        />
      </View>
    </Card>
  );
}

function RedlineListItem({ x, reload }: { x: R; reload: () => void }) {
  const statusCol =
    x.STATUS === 'APPROVED' || x.STATUS === 'SENT_TO_AE' ? colors.warn :
    x.STATUS === 'INCORPORATED' || x.STATUS === 'CLOSED' ? colors.ok :
    x.STATUS === 'REJECTED' ? colors.danger : colors.muted;

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
        <Badge text={x.STATUS} color={statusCol} />
      </Row>

      <Text style={{ color: colors.text, fontWeight: '600', fontSize: 13.5 }}>{x.MARKUP}</Text>
      <KV k="Was" v={x.CHANGE_FROM} />
      <KV k="Now" v={x.CHANGE_TO} />

      {x.PDF_URL ? (
        <Row style={{ marginTop: space(1) }}>
          <Button
            small
            kind="secondary"
            title="Open red-marked CD (PDF)"
            onPress={() => Linking.openURL(authedUrl(x.PDF_URL))}
          />
        </Row>
      ) : null}

      <View style={{ marginTop: space(1) }}>
        <WorkflowActions
          actions={x.ACTIONS ?? []}
          endpoint={`/redlines/${x.REDLINE_ID}/transition`}
          entity="REDLINE"
          onDone={reload}
        />
      </View>
    </Card>
  );
}

export default function RfisScreen() {
  const { can } = useAuth();
  const allowed = can('ADMIN', 'AE_ENGINEER');
  const rfis = useApi<R[]>(allowed ? '/rfis' : null);
  const redlines = useApi<R[]>(allowed ? '/redlines' : null);

  const [section, setSection] = useState<'RFIS' | 'REDLINES'>('RFIS');
  const [rfiFilter, setRfiFilter] = useState<'ALL' | 'SUBMITTED' | 'DRAFT' | 'ANSWERED' | 'CLOSED'>('ALL');
  const [redFilter, setRedFilter] = useState<'ALL' | 'APPROVED' | 'SENT_TO_AE' | 'ACKNOWLEDGED' | 'INCORPORATED' | 'REJECTED'>('ALL');
  const [query, setQuery] = useState('');

  if (!allowed) {
    return (
      <View style={[s.screen, { alignItems: 'center', justifyContent: 'center', padding: space(8) }]}>
        <IconBadge name="lock" color={colors.muted} size={56} />
        <Text style={{ fontWeight: '800', fontSize: 18, color: colors.text, marginTop: space(3) }}>Restricted access</Text>
        <Muted>Only administrators and A&E Engineers can access the Redlines & RFIs tab.</Muted>
      </View>
    );
  }

  const rfiList = rfis.data ?? [];
  const redList = redlines.data ?? [];

  const rfiCounts = useMemo(() => ({
    ALL: rfiList.length,
    SUBMITTED: rfiList.filter((x) => x.STATUS === 'SUBMITTED').length,
    DRAFT: rfiList.filter((x) => x.STATUS === 'DRAFT').length,
    ANSWERED: rfiList.filter((x) => x.STATUS === 'ANSWERED').length,
    CLOSED: rfiList.filter((x) => x.STATUS === 'CLOSED').length,
  }), [rfiList]);

  const redCounts = useMemo(() => ({
    ALL: redList.length,
    APPROVED: redList.filter((x) => x.STATUS === 'APPROVED').length,
    SENT_TO_AE: redList.filter((x) => x.STATUS === 'SENT_TO_AE').length,
    ACKNOWLEDGED: redList.filter((x) => x.STATUS === 'ACKNOWLEDGED').length,
    INCORPORATED: redList.filter((x) => x.STATUS === 'INCORPORATED').length,
    REJECTED: redList.filter((x) => x.STATUS === 'REJECTED').length,
  }), [redList]);

  const filteredRfis = useMemo(() => {
    let list = rfiList;
    if (rfiFilter !== 'ALL') {
      list = list.filter((x) => x.STATUS === rfiFilter);
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
    if (redFilter !== 'ALL') {
      list = list.filter((x) => x.STATUS === redFilter);
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
          { key: 'RFIS', label: `RFIs (${rfiCounts.ALL})` },
          { key: 'REDLINES', label: `Redlines (${redCounts.ALL})` },
        ]}
      />

      {/* Sub filters and search */}
      <Row style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
        {section === 'RFIS' ? (
          <Chips
            value={rfiFilter}
            onChange={setRfiFilter}
            options={[
              { key: 'ALL', label: `All (${rfiCounts.ALL})` },
              { key: 'SUBMITTED', label: `Submitted (${rfiCounts.SUBMITTED})` },
              { key: 'DRAFT', label: `Draft (${rfiCounts.DRAFT})` },
              { key: 'ANSWERED', label: `Answered (${rfiCounts.ANSWERED})` },
              { key: 'CLOSED', label: `Closed (${rfiCounts.CLOSED})` },
            ]}
          />
        ) : (
          <Chips
            value={redFilter}
            onChange={setRedFilter}
            options={[
              { key: 'ALL', label: `All (${redCounts.ALL})` },
              { key: 'SENT_TO_AE', label: `Sent to A&E (${redCounts.SENT_TO_AE})` },
              { key: 'APPROVED', label: `Approved (${redCounts.APPROVED})` },
              { key: 'ACKNOWLEDGED', label: `Acknowledged (${redCounts.ACKNOWLEDGED})` },
              { key: 'INCORPORATED', label: `Incorporated (${redCounts.INCORPORATED})` },
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
            <Empty text={query ? 'No RFIs match your search.' : `No ${rfiFilter === 'ALL' ? '' : rfiFilter} RFIs found.`} />
          ) : null}
          {filteredRfis.map((r) => (
            <RfiListItem key={r.RFI_ID} r={r} reload={rfis.reload} />
          ))}
        </>
      ) : (
        <>
          {!loading && !filteredRedlines.length ? (
            <Empty text={query ? 'No redlines match your search.' : `No ${redFilter === 'ALL' ? '' : redFilter} redlines found.`} />
          ) : null}
          {filteredRedlines.map((x) => (
            <RedlineListItem key={x.REDLINE_ID} x={x} reload={redlines.reload} />
          ))}
        </>
      )}
    </ScrollView>
  );
}
