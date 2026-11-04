// Discrepancy workbench: what was expected vs found, which document governs, the evidence, then
// confirm / dismiss / redline / RFI / adjust BOM with a reason code. History and comments are audited.
import { router, Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { Image, RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';
import { ActionPill, CompareStrip, eventLabel, FAMILY, fixOf, Panel, RuleCode, sevOf, WhereChip } from '../../components/site/FindingView';
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
  const found = Array.isArray(x.FOUND?.v) && x.FOUND.v.length > 0 && typeof x.FOUND.v[0] === 'object' && x.FOUND.v[0] !== null && 'field' in x.FOUND.v[0] ? (x.FOUND.v as R[]) : null;
  const isRedlineRemoved = x.AE_STATUS === 'REDLINE_REMOVED' || x.STATUS === 'CLOSED' || (x.STATUS === 'RESOLVED' && !x.REDLINE_PENDING_REMOVAL);
  const isAeRevised = !isRedlineRemoved && (x.AE_STATUS === 'IMPROVED_REV_RECEIVED' || x.REASON_CODE === 'RC-AE-REVISED' || x.REDLINE_PENDING_REMOVAL);
  const isSentToAe = !isRedlineRemoved && !isAeRevised && (x.AE_STATUS === 'SENT_TO_AE' || x.STATUS === 'REDLINED');
  const revLabel = x.AE_REVISION_LABEL || 'REV 2';

  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={d.loading} onRefresh={d.reload} />}>
      <Stack.Screen options={{ title: `${x.SITE_ID} ${x.RULE_ID}` }} />
      <View style={{ flexDirection: 'row', backgroundColor: colors.card, borderRadius: 18, marginBottom: space(3), borderWidth: 1, borderColor: isRedlineRemoved ? '#86efac' : isAeRevised ? '#10b981' : isSentToAe ? '#3b82f6' : colors.border, overflow: 'hidden' }}>
        <View style={{ width: 6, backgroundColor: isRedlineRemoved ? '#10b981' : isAeRevised ? '#10b981' : sev.color }} />
        <View style={{ flex: 1, padding: space(5), gap: space(3) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: space(2) }}>
            {isRedlineRemoved ? (
              <Badge text="RESOLVED" color={colors.ok} />
            ) : (
              <Badge text={`${sev.label} severity`} color={sev.color} />
            )}
            {isRedlineRemoved ? (
              <Badge text={`${revLabel} UPDATED`} color={colors.ok} />
            ) : isAeRevised ? (
              <Badge text={`${revLabel} RECEIVED`} color={colors.ok} />
            ) : isSentToAe ? (
              <Badge text="SENT TO A&E" color={colors.primary} />
            ) : (
              <Badge text={x.STATUS} />
            )}
            <Text style={{ fontSize: 12, color: colors.muted }}>{FAMILY[x.FAMILY] ?? x.FAMILY}</Text>
            <RuleCode code={x.RULE_ID} />
          </View>
          <Text style={{ fontSize: 22, fontWeight: '800', color: colors.text, letterSpacing: -0.4, lineHeight: 29 }}>{x.TITLE}</Text>
          <WhereChip x={x} />
        </View>
      </View>

      {isRedlineRemoved ? (
        <View style={{ backgroundColor: '#f0fdf4', borderColor: '#86efac', borderWidth: 1, borderRadius: 14, padding: space(4), marginBottom: space(3), gap: space(2) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2) }}>
            <Icon name="check-circle" size={18} color="#16a34a" />
            <Text style={{ fontSize: 15, fontWeight: '800', color: '#15803d' }}>Resolved in {revLabel} • Redline updated & removed</Text>
          </View>
          <Text style={{ fontSize: 13, color: '#166534', lineHeight: 20 }}>
            A&E updated the CD drawing ({revLabel}) matching measured values. The redline markup has been verified and removed.
          </Text>
        </View>
      ) : null}

      {isAeRevised ? (
        <View style={{ backgroundColor: '#ecfdf5', borderColor: '#10b981', borderWidth: 1, borderRadius: 14, padding: space(4), marginBottom: space(3), gap: space(2) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2) }}>
              <Icon name="check-circle" size={18} color="#059669" />
              <Text style={{ fontSize: 15, fontWeight: '800', color: '#065f46' }}>Improved version ({revLabel}) received from A&E</Text>
            </View>
            {can('SCOPER', 'REVIEWER', 'ADMIN') ? (
              <Button small title="Remove redline & Close" onPress={() => post(`/discrepancies/${id}/remove-redline`, {})} />
            ) : null}
          </View>
          <Text style={{ fontSize: 13, color: '#047857', lineHeight: 20 }}>
            A&E updated the CD drawing ({revLabel}) matching measured values. This discrepancy will remain visible in the Discrepancies list until you verify and remove the redline.
          </Text>
        </View>
      ) : null}

      {isSentToAe && !isAeRevised ? (
        <View style={{ backgroundColor: '#eff6ff', borderColor: '#3b82f6', borderWidth: 1, borderRadius: 14, padding: space(4), marginBottom: space(3), gap: space(2) }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2) }}>
              <Icon name="send" size={16} color="#2563eb" />
              <Text style={{ fontSize: 14, fontWeight: '700', color: '#1e40af' }}>Sent to A&E • In review for revised CD</Text>
            </View>
            {can('AE_ENGINEER', 'ADMIN') ? (
              <Button small title="Send improved REV 2" onPress={() => post(`/discrepancies/${id}/submit-ae-revision`, { revision: 'REV 2', comment: 'Improved CD revision incorporating drone measurements' })} />
            ) : null}
          </View>
        </View>
      ) : null}
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
          {!isSentToAe && !isAeRevised && x.STATUS !== 'CLOSED' && can('SCOPER', 'REVIEWER', 'ADMIN') ? (
            <View style={{ marginTop: space(2) }}>
              <Button small title="Send to A&E for drawing revision" onPress={() => post(`/discrepancies/${id}/send-to-ae`, {})} />
            </View>
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
        <Card>
          {x.HISTORY && x.HISTORY.length ? (
            x.HISTORY.map((h, i) => (
              <KV
                key={h.EVENT_ID || i}
                k={when(h.EVENT_TS)}
                v={`${eventLabel(h, revLabel)}${h.COMMENT ? ` • "${h.COMMENT}"` : ''}`}
              />
            ))
          ) : (
            <Muted>No actions yet</Muted>
          )}
        </Card>
      </Section>
    </ScrollView>
  );
}
