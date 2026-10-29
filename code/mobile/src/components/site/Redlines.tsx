import React, { useState } from 'react';
import { Image, Linking, Modal, Platform, Pressable, Text, TextInput, View } from 'react-native';
import { api, ApiError, authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { when } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, space } from '../theme';
import { Badge, Button, Card, Empty, ErrorView, IconBadge, KV, Loading, Muted, Row, s, Section, Title } from '../ui';
import { WorkflowActions } from '../WorkflowActions';

function formatRole(role?: string): string {
  if (!role) return '';
  if (role === 'ADMIN') return 'Admin';
  if (role === 'AE_ENGINEER') return 'A&E Engineer';
  if (role === 'SCOPER') return 'Scoper';
  if (role === 'REVIEWER') return 'Reviewer';
  return role.replace(/_/g, ' ');
}

export function RfiCard({ r, reload }: { r: R; reload: () => void }) {
  const { can, user } = useAuth();
  const [answer, setAnswer] = useState(r.PROPOSED_ANSWER ?? '');
  const [err, setErr] = useState<ApiError | null>(null);
  const send = async () => {
    try {
      await api.post(`/rfis/${r.RFI_ID}/answer`, { answer });
      reload();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  const toParty = r.TO_PARTY === 'AE_ENGINEER' ? 'For A&E ENGINEER' : 'For Admin';
  const displayStatus =
    r.STATUS === 'SUBMITTED' ? 'REQUEST' :
    r.STATUS === 'IN_REVIEW' ? 'IN REVIEW' :
    r.STATUS === 'ANSWERED' ? 'ANSWERED' :
    r.STATUS === 'CLOSED' ? 'CLOSED' :
    r.STATUS;
  const statusColor =
    r.STATUS === 'SUBMITTED' ? colors.primary :
    r.STATUS === 'IN_REVIEW' ? colors.warn :
    r.STATUS === 'ANSWERED' || r.STATUS === 'CLOSED' ? colors.ok :
    colors.muted;

  return (
    <Card>
      <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <Title>{toParty}</Title>
        <Badge text={displayStatus} color={statusColor} />
      </Row>
      <Text style={{ color: colors.text, fontWeight: '700', fontSize: 14 }}>{r.SUBJECT}</Text>
      <Muted style={{ color: colors.text }}>{r.QUESTION}</Muted>
      {r.PROPOSED_ANSWER ? <KV k="Proposed answer" v={r.PROPOSED_ANSWER} /> : null}
      {r.ANSWER ? <KV k="Answer" v={r.ANSWER} /> : null}
      {(r.ACTIONS ?? []).some((a: string) => a !== 'ANSWER') ? (
        <View style={{ marginTop: space(2) }}>
          <WorkflowActions actions={(r.ACTIONS ?? []).filter((a: string) => a !== 'ANSWER')} endpoint={`/rfis/${r.RFI_ID}/transition`} entity="RFI" onDone={reload} />
        </View>
      ) : null}
      {(can('ADMIN', 'ERICSSON') || (user?.role === 'AE_ENGINEER' && r.TO_PARTY === 'AE_ENGINEER')) && r.STATUS === 'IN_REVIEW' ? (
        <View style={{ marginTop: space(2), gap: space(2) }}>
          <TextInput style={[s.input, { minHeight: 60 }]} multiline value={answer} onChangeText={setAnswer} placeholder="Answer" />
          <Button small title="Send answer" disabled={!answer.trim()} onPress={send} />
          {err ? <ErrorView error={err} /> : null}
        </View>
      ) : null}
    </Card>
  );
}

/** The drone footage that backs a redline: the video frame (or still) that looks at the place the redline is about. */
function ProofStrip({ proof }: { proof: R[] }) {
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
      <Row style={{ flexWrap: 'wrap', alignItems: 'flex-start', gap: space(3) }}>
        {drone.map((p) => (
          <Pressable key={p.PROOF_ID} onPress={() => setBig(p)} accessibilityRole="button" accessibilityLabel={`Enlarge: ${p.CAPTION}`} style={{ width: 280, gap: 4 }}>
            <Image source={{ uri: authedUrl(p.URL) }} resizeMode="cover" style={{ width: 280, height: 158, borderRadius: 10, backgroundColor: colors.border }} />
            <Badge text={p.KIND === 'VIDEO' ? 'Drone video' : 'Drone still'} />
            <Muted style={{ color: colors.text, fontWeight: '600' }}>{p.CAPTION}</Muted>
            <Muted>{p.BASIS}</Muted>
          </Pressable>
        ))}
      </Row>
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
function PdfPreview({ path }: { path: string }) {
  const [open, setOpen] = useState(true);
  const url = authedUrl(path);
  const name = decodeURIComponent(path.split('/').pop()?.split('?')[0] ?? 'Redlined drawing');
  return (
    <Card style={{ marginBottom: space(3) }}>
      <Row style={{ justifyContent: 'space-between', alignItems: 'center', gap: space(2) }}>
        <Row style={{ flex: 1, minWidth: 220, gap: space(3) }}>
          <IconBadge name="file-text" color={colors.danger} size={40} />
          <View style={{ flex: 1 }}>
            <Title style={{ fontSize: 16 }}>Redlined drawing</Title>
            <Muted numberOfLines={1}>{name}</Muted>
          </View>
        </Row>
        <Row>
          <Button small kind="secondary" title={open ? 'Hide preview' : 'Show preview'} onPress={() => setOpen((v) => !v)} />
          <Button small title="Open in new tab" onPress={() => Linking.openURL(url)} />
        </Row>
      </Row>
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

export function Redlines({ siteId }: { siteId: string }) {
  const { user } = useAuth();
  const red = useApi<R[]>(`/redlines?site_id=${siteId}`);
  const rfis = useApi<R[]>(`/rfis?site_id=${siteId}`);
  if (red.error) return <ErrorView error={red.error} onRetry={red.reload} />;
  if (!red.data || !rfis.data) return <Loading />;
  const pdf = red.data.find((x) => x.PDF_URL)?.PDF_URL;
  return (
    <View>
      {pdf ? <PdfPreview path={pdf} /> : null}
      <Section title={`Redlines (${red.data.length})`}>
        {!red.data.length ? <Empty text="No redlines for this site." /> : null}
        {red.data.map((x, i) => {
          const st =
            ['IN_REVIEW', 'APPROVED', 'SENT_TO_AE', 'DRAFT'].includes(x.STATUS) ? 'IN_REVIEW' :
            ['WORK_QUEUE', 'ACKNOWLEDGED'].includes(x.STATUS) ? 'WORK_QUEUE' :
            ['COMPLETED', 'INCORPORATED', 'CLOSED'].includes(x.STATUS) ? 'COMPLETED' :
            x.STATUS;
          const statusCol =
            st === 'IN_REVIEW' ? colors.warn :
            st === 'WORK_QUEUE' ? colors.primary :
            st === 'COMPLETED' ? colors.ok :
            st === 'REJECTED' ? colors.danger : colors.muted;

          return (
            <Card key={x.REDLINE_ID}>
              <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                <Row style={{ gap: space(2), alignItems: 'center', flexWrap: 'wrap', flex: 1 }}>
                  <Title>{`${i + 1}. ${x.DOC_TYPE} ${x.DOC_REVISION ?? ''} sheet ${x.SHEET}`}</Title>
                  {x.LAST_RESPONSE ? (
                    <Badge
                      text={`Responded by ${formatRole(x.LAST_RESPONSE.ACTOR_ROLE)} (${x.LAST_RESPONSE.ACTOR_USER_ID})`}
                      color={x.LAST_RESPONSE.ACTOR_ROLE === 'ADMIN' ? colors.primary : colors.accent}
                    />
                  ) : (
                    <Badge text="For Admin & A&E" color={colors.muted} />
                  )}
                </Row>
                <Badge text={st.replace('_', ' ')} color={statusCol} />
              </Row>
              <Muted style={{ color: colors.text }}>{x.MARKUP}</Muted>
              <KV k="Was" v={x.CHANGE_FROM} />
              <KV k="Now" v={x.CHANGE_TO} />
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

              {x.LAST_RESPONSE ? (
                <View
                  style={{
                    marginTop: space(2),
                    padding: space(2.5),
                    backgroundColor: (x.LAST_RESPONSE.ACTOR_ROLE === 'ADMIN' ? colors.primary : colors.accent) + '12',
                    borderRadius: 8,
                    borderLeftWidth: 3,
                    borderLeftColor: x.LAST_RESPONSE.ACTOR_ROLE === 'ADMIN' ? colors.primary : colors.accent,
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
                    {`  ➔  Status: `}<Text style={{ fontWeight: '700', color: statusCol }}>{st.replace('_', ' ')}</Text>
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

              <ProofStrip proof={x.PROOF ?? []} />
              {['AE_ENGINEER', 'ADMIN'].includes(user?.role ?? '') && (x.ACTIONS ?? []).length ? (
                <View style={{ marginTop: space(3) }}>
                  <WorkflowActions actions={x.ACTIONS} endpoint={`/redlines/${x.REDLINE_ID}/transition`} entity="REDLINE" onDone={red.reload} />
                </View>
              ) : null}
            </Card>
          );
        })}
      </Section>
      <Section title={`RFIs (${rfis.data.length})`}>
        {!rfis.data.length ? <Empty text="No RFIs for this site." /> : null}
        {rfis.data.map((r) => <RfiCard key={r.RFI_ID} r={r} reload={rfis.reload} />)}
      </Section>
    </View>
  );
}
