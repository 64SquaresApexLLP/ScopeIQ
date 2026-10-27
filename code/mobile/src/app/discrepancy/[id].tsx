// Discrepancy workbench: what was expected vs found, which document governs, the evidence, then
// confirm / dismiss / redline / RFI / adjust BOM with a reason code. History and comments are audited.
import { router, Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { Image, RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';
import { ActionPill, CompareStrip, FAMILY, fixOf, Panel, RuleCode, sevOf, WhereChip } from '../../components/site/FindingView';
import { colors, space } from '../../components/theme';
import { Badge, Button, Card, ErrorView, Icon, KV, Loading, Muted, Row, s, Section, Title } from '../../components/ui';
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
  const sev = sevOf(x);
  const found = Array.isArray(x.FOUND?.v) && x.FOUND.v.length && 'field' in x.FOUND.v[0] ? (x.FOUND.v as R[]) : null;
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={d.loading} onRefresh={d.reload} />}>
      <Stack.Screen options={{ title: `${x.SITE_ID} ${x.RULE_ID}` }} />
      <View style={{ flexDirection: 'row', backgroundColor: colors.card, borderRadius: 18, marginBottom: space(3), borderWidth: 1, borderColor: colors.border, overflow: 'hidden' }}>
        <View style={{ width: 6, backgroundColor: sev.color }} />
        <View style={{ flex: 1, padding: space(5), gap: space(3) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: space(2) }}>
            <Badge text={`${sev.label} severity`} color={sev.color} />
            <Badge text={x.STATUS} />
            <Text style={{ fontSize: 12, color: colors.muted }}>{FAMILY[x.FAMILY] ?? x.FAMILY}</Text>
            <RuleCode code={x.RULE_ID} />
          </View>
          <Text style={{ fontSize: 22, fontWeight: '800', color: colors.text, letterSpacing: -0.4, lineHeight: 29 }}>{x.TITLE}</Text>
          <WhereChip x={x} />
        </View>
      </View>
      <Panel icon="search" title="What we found">
        <CompareStrip x={x} large />
        {x.DESCRIPTION ? <Text style={{ fontSize: 14, lineHeight: 22, color: colors.text, marginTop: space(3) }}>{x.DESCRIPTION}</Text> : null}
        {found ? (
          <View style={{ marginTop: space(2) }}>
            <Muted>Values to review</Muted>
            {found.map((f, i) => <KV key={i} k={String(f.field ?? i)} v={`${show(f.value)}  (${Math.round(Number(f.confidence ?? 0) * 100)}%${f.page ? `, ${f.page}` : ''})`} />)}
          </View>
        ) : null}
      </Panel>
      <Panel icon="check-circle" title="What to do next">
        <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: space(2) }}>
          <ActionPill x={x} />
          {fixOf(x) ? <Text style={{ fontSize: 13, color: colors.muted }}>{`Fix in ${fixOf(x)}`}</Text> : null}
        </View>
        <View style={{ marginTop: space(2) }}>
          {x.BOM_IMPACT && !/^none/i.test(x.BOM_IMPACT) ? <KV k="BOM impact" v={x.BOM_IMPACT} /> : null}
          {x.GOVERNING ? <KV k="Governing source" v={x.GOVERNING} /> : null}
          {x.REASON_CODE ? <KV k="Reason code" v={x.REASON_CODE} /> : null}
          {x.ASSIGNED_TO ? <KV k="Assigned to" v={x.ASSIGNED_TO} /> : null}
        </View>
      </Panel>
      <Panel icon="layers" title="Sources compared">
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(2) }}>
          {(x.SOURCES ?? []).map((src: string) => (
            <View key={src} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.surfaceAlt, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: colors.border }}>
              <Icon name="file-text" size={13} color={colors.muted} />
              <Text style={{ fontSize: 12, fontWeight: '600', color: colors.text }}>{src}</Text>
            </View>
          ))}
        </View>
        {x.CONFIDENCE != null ? <Muted style={{ marginTop: space(2) }}>{`Confidence ${Math.round(x.CONFIDENCE * 100)}%`}</Muted> : null}
      </Panel>
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
