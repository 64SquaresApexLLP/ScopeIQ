// Discrepancy workbench: what was expected vs found, which document governs, the evidence, then
// confirm / dismiss / redline / RFI / adjust BOM with a reason code. History and comments are audited.
import { router, Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { Image, RefreshControl, ScrollView, TextInput, View } from 'react-native';
import { colors, space } from '../../components/theme';
import { Badge, Button, Card, ErrorView, KV, Loading, Muted, Row, s, Section, Title } from '../../components/ui';
import { WorkflowActions } from '../../components/WorkflowActions';
import { api, ApiError } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { show, when } from '../../lib/format';
import { Row as R, WorkflowAction } from '../../lib/types';
import { useApi } from '../../lib/useApi';

export default function Discrepancy() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const d = useApi<R & { ACTIONS: WorkflowAction[]; HISTORY: R[]; COMMENTS: R[]; REDLINES: R[]; EVIDENCE_URLS: string[] }>(`/discrepancies/${id}`);
  const { user, can } = useAuth();
  const [text, setText] = useState('');
  const [err, setErr] = useState<ApiError | null>(null);

  const post = async (path: string, body: unknown) => {
    setErr(null);
    try {
      await api.post(path, body);
      await d.reload();
    } catch (e) {
      setErr(e as ApiError);
    }
  };

  if (d.error) return <View style={s.content}><ErrorView error={d.error} onRetry={d.reload} /></View>;
  if (!d.data) return <Loading />;
  const x = d.data;
  const found = Array.isArray(x.FOUND?.v) && x.FOUND.v.length && 'field' in x.FOUND.v[0] ? (x.FOUND.v as R[]) : null;
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={d.loading} onRefresh={d.reload} />}>
      <Stack.Screen options={{ title: `${x.SITE_ID} ${x.RULE_ID}` }} />
      <Card>
        <Row><Badge text={x.SEVERITY} /><Badge text={x.STATUS} /><Badge text={x.OUTCOME} color={colors.primary} /><Badge text={x.FAMILY} color={colors.muted} /></Row>
        <Title style={{ marginTop: space(2) }}>{x.TITLE}</Title>
        <Muted style={{ color: colors.text, marginTop: 4 }}>{x.DESCRIPTION}</Muted>
      </Card>
      <Section title="Comparison">
        <Card>
          {x.SECTOR ? <KV k="Location" v={`Sector ${x.SECTOR}${x.POSITION ? `, position ${x.POSITION}` : ''}`} /> : null}
          <KV k="Expected" v={show(x.EXPECTED)} />
          {!found ? <KV k="Found" v={show(x.FOUND)} /> : null}
          <KV k="Governing source" v={x.GOVERNING || '-'} />
          <KV k="Sources compared" v={(x.SOURCES ?? []).join(', ')} />
          <KV k="Fix in" v={`${x.TARGET_DOC ?? '-'}${x.TARGET_SHEET ? ` sheet ${x.TARGET_SHEET}` : ''}`} />
          <KV k="BOM impact" v={x.BOM_IMPACT} />
          <KV k="Confidence" v={x.CONFIDENCE != null ? `${Math.round(x.CONFIDENCE * 100)}%` : '-'} />
          <KV k="Reason code" v={x.REASON_CODE} />
          <KV k="Assigned to" v={x.ASSIGNED_TO} />
        </Card>
        {found ? (
          <Card>
            <Muted>Values to review</Muted>
            {found.map((f, i) => <KV key={i} k={String(f.field ?? i)} v={`${show(f.value)}  (${Math.round(Number(f.confidence ?? 0) * 100)}%${f.page ? `, ${f.page}` : ''})`} />)}
          </Card>
        ) : null}
      </Section>
      {x.EVIDENCE_URLS?.length ? (
        <Section title="Evidence">
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(2) }}>
            {x.EVIDENCE_URLS.map((u) => <Image key={u} source={{ uri: api.fileUrl(u) }} style={{ width: '48%', aspectRatio: 16 / 9, borderRadius: 6 }} />)}
          </View>
        </Section>
      ) : null}
      <Section title="Actions">
        <Card>
          <WorkflowActions actions={x.ACTIONS} endpoint={`/discrepancies/${id}/transition`} entity="DISCREPANCY" onDone={d.reload} />
          {can('SCOPER', 'REVIEWER') && x.ASSIGNED_TO !== user?.user_id ? (
            <View style={{ marginTop: space(2) }}><Button small kind="secondary" title="Assign to me" onPress={() => post(`/discrepancies/${id}/assign`, { user_id: user?.user_id })} /></View>
          ) : null}
          {err ? <ErrorView error={err} /> : null}
        </Card>
      </Section>
      {x.REDLINES?.length ? (
        <Section title="Redlines">
          {x.REDLINES.map((r) => (
            <Card key={r.REDLINE_ID} onPress={() => router.push({ pathname: '/site/[id]', params: { id: x.SITE_ID, tab: 'redlines' } })}>
              <Row style={{ justifyContent: 'space-between' }}><Title>{`${r.DOC_TYPE} sheet ${r.SHEET}`}</Title><Badge text={r.STATUS} /></Row>
              <Muted>{r.MARKUP}</Muted>
            </Card>
          ))}
        </Section>
      ) : null}
      <Section title="Comments">
        {x.COMMENTS.map((c) => <Card key={c.COMMENT_ID}><Muted>{`${c.USER_ID} - ${when(c.CREATED_AT)}`}</Muted><Muted style={{ color: colors.text }}>{c.COMMENT_TEXT}</Muted></Card>)}
        <TextInput style={[s.input, { minHeight: 60 }]} multiline placeholder="Add a comment" value={text} onChangeText={setText} />
        <View style={{ marginTop: space(2) }}><Button small title="Add comment" disabled={!text.trim()} onPress={async () => { await post(`/discrepancies/${id}/comments`, { text }); setText(''); }} /></View>
      </Section>
      <Section title="History">
        <Card>{x.HISTORY.length ? x.HISTORY.map((h) => <KV key={h.EVENT_ID} k={when(h.EVENT_TS)} v={`${h.FROM_STATE} -> ${h.TO_STATE} by ${h.ACTOR_USER_ID}${h.REASON_CODE ? ` (${h.REASON_CODE})` : ''}${h.COMMENT ? `: ${h.COMMENT}` : ''}`} />) : <Muted>No actions yet</Muted>}</Card>
      </Section>
    </ScrollView>
  );
}
