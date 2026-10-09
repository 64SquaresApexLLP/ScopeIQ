import React, { useState } from 'react';
import { Linking, TextInput, View } from 'react-native';
import { api, ApiError, authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, space } from '../theme';
import { Badge, Button, Card, Empty, ErrorView, KV, Loading, Muted, Row, s, Section, Title } from '../ui';
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
      <View style={{ marginTop: space(2) }}>
        <WorkflowActions actions={(r.ACTIONS ?? []).filter((a: string) => a !== 'ANSWER')} endpoint={`/rfis/${r.RFI_ID}/transition`} entity="RFI" onDone={reload} />
      </View>
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

export function Redlines({ siteId }: { siteId: string }) {
  const red = useApi<R[]>(`/redlines?site_id=${siteId}`);
  const rfis = useApi<R[]>(`/rfis?site_id=${siteId}`);
  if (red.error) return <ErrorView error={red.error} onRetry={red.reload} />;
  if (!red.data || !rfis.data) return <Loading />;
  const pdf = red.data.find((x) => x.PDF_URL)?.PDF_URL;
  return (
    <View>
      {pdf ? <Button title="Open red-marked CD (PDF)" onPress={() => Linking.openURL(authedUrl(pdf))} /> : null}
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
            <View style={{ marginTop: space(2) }}>
              <WorkflowActions actions={x.ACTIONS ?? []} endpoint={`/redlines/${x.REDLINE_ID}/transition`} entity="REDLINE" onDone={red.reload} />
            </View>
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
