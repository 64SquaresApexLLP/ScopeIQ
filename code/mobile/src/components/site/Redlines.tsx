import React, { useState } from 'react';
import { Image, Linking, Modal, Platform, Pressable, TextInput, View } from 'react-native';
import { api, ApiError, authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, space } from '../theme';
import { Badge, Button, Card, Empty, ErrorView, IconBadge, KV, Loading, Muted, Row, s, Section, Title } from '../ui';
import { WorkflowActions } from '../WorkflowActions';
import { ImplementChanges } from './ImplementChanges';

function RfiCard({ r, reload }: { r: R; reload: () => void }) {
  const { can } = useAuth();
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
  return (
    <Card>
      <Row style={{ justifyContent: 'space-between' }}><Title>{`To ${r.TO_PARTY}`}</Title><Badge text={r.STATUS} /></Row>
      <Muted style={{ color: colors.text, fontWeight: '600' }}>{r.SUBJECT}</Muted>
      <Muted style={{ color: colors.text }}>{r.QUESTION}</Muted>
      {r.PROPOSED_ANSWER ? <KV k="Proposed answer" v={r.PROPOSED_ANSWER} /> : null}
      {r.ANSWER ? <KV k="Answer" v={r.ANSWER} /> : null}
      {(r.ACTIONS ?? []).some((a: string) => a !== 'ANSWER') ? (
        <View style={{ marginTop: space(2) }}>
          <WorkflowActions actions={(r.ACTIONS ?? []).filter((a: string) => a !== 'ANSWER')} endpoint={`/rfis/${r.RFI_ID}/transition`} entity="RFI" onDone={reload} />
        </View>
      ) : null}
      {can('ERICSSON') && (r.ACTIONS ?? []).includes('ANSWER') ? (
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
  if (!proof.length) {
    return <Muted style={{ marginTop: space(2) }}>No drone footage faces this place, so there is no picture to attach.</Muted>;
  }
  return (
    <View style={{ marginTop: space(3), gap: space(2) }}>
      <Muted style={{ fontWeight: '700', color: colors.text }}>Proof from the drone survey</Muted>
      <Row style={{ flexWrap: 'wrap', alignItems: 'flex-start', gap: space(3) }}>
        {proof.map((p) => (
          <Pressable key={p.PROOF_ID} onPress={() => setBig(p)} accessibilityRole="button" accessibilityLabel={`Enlarge: ${p.CAPTION}`} style={{ width: 280, gap: 4 }}>
            <Image source={{ uri: authedUrl(p.URL) }} resizeMode="cover" style={{ width: 280, height: 158, borderRadius: 10, backgroundColor: colors.border }} />
            <Badge text={p.KIND === 'VIDEO' ? 'Drone video' : 'Drone still'} />
            <Muted style={{ color: colors.text, fontWeight: '600' }}>{p.CAPTION}</Muted>
            <Muted>{p.BASIS}</Muted>
          </Pressable>
        ))}
      </Row>
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
  const red = useApi<R[]>(`/redlines?site_id=${siteId}`);
  const rfis = useApi<R[]>(`/rfis?site_id=${siteId}`);
  if (red.error) return <ErrorView error={red.error} onRetry={red.reload} />;
  if (!red.data || !rfis.data) return <Loading />;
  const pdf = red.data.find((x) => x.PDF_URL)?.PDF_URL;
  return (
    <View>
      {pdf ? <PdfPreview path={pdf} /> : null}
      {/* re-read the approved count when a redline changes */}
      <ImplementChanges key={red.data.map((x) => x.STATUS).join(',')} siteId={siteId} />
      <Section title={`Redlines (${red.data.length})`}>
        {!red.data.length ? <Empty text="No redlines for this site." /> : null}
        {red.data.map((x, i) => (
          <Card key={x.REDLINE_ID}>
            <Row style={{ justifyContent: 'space-between' }}><Title>{`${i + 1}. ${x.DOC_TYPE} ${x.DOC_REVISION ?? ''} sheet ${x.SHEET}`}</Title><Badge text={x.STATUS} /></Row>
            <Muted style={{ color: colors.text }}>{x.MARKUP}</Muted>
            <KV k="Was" v={x.CHANGE_FROM} />
            <KV k="Now" v={x.CHANGE_TO} />
            <ProofStrip proof={x.PROOF ?? []} />
            {(x.ACTIONS ?? []).length ? (
              <View style={{ marginTop: space(3) }}>
                <WorkflowActions actions={x.ACTIONS} endpoint={`/redlines/${x.REDLINE_ID}/transition`} entity="REDLINE" onDone={red.reload} />
              </View>
            ) : null}
          </Card>
        ))}
      </Section>
      <Section title={`RFIs (${rfis.data.length})`}>
        {!rfis.data.length ? <Empty text="No RFIs for this site." /> : null}
        {rfis.data.map((r) => <RfiCard key={r.RFI_ID} r={r} reload={rfis.reload} />)}
      </Section>
    </View>
  );
}
