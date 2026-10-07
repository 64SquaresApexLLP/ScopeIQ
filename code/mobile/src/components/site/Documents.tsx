import { router } from 'expo-router';
import React from 'react';
import { Linking, View } from 'react-native';
import { authedUrl } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors } from '../theme';
import { Badge, Button, Card, ErrorView, Loading, Muted, Row, Section, Title } from '../ui';

export function Documents({ siteId }: { siteId: string }) {
  const { can } = useAuth();
  const d = useApi<{ documents: R[]; uploads: R[] }>(`/sites/${siteId}/documents`);
  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading />;
  return (
    <View>
      {can('SCOPER', 'AE_ENGINEER', 'DRONE_VENDOR', 'CX_SP', 'ERICSSON') ? (
        <Button title="Upload a document" onPress={() => router.push({ pathname: '/upload/[siteId]', params: { siteId } })} />
      ) : null}
      <Section title={`Registered documents (${d.data.documents.length})`}>
        {d.data.documents.map((x) => (
          <Card key={x.DOC_ID} onPress={() => Linking.openURL(authedUrl(`/documents/${x.DOC_ID}/download`))}>
            <Row style={{ justifyContent: 'space-between' }}><Title>{x.DOC_TYPE}</Title>
              <Row><Badge text={x.STATUS} color={x.STATUS === 'CURRENT' ? colors.ok : colors.muted} />{x.SOURCE === 'upload' ? <Badge text="uploaded" color={colors.info} /> : null}</Row></Row>
            <Muted>{`${x.FILE_NAME}  ${x.REVISION ? `(${x.REVISION})` : ''}  ${Math.round((x.SIZE_BYTES ?? 0) / 1024)} KB`}</Muted>
          </Card>
        ))}
      </Section>
      {d.data.uploads.length ? (
        <Section title="Uploads">
          {d.data.uploads.map((u) => (
            <Card key={u.UPLOAD_ID}><Row style={{ justifyContent: 'space-between' }}><Title>{u.FILE_NAME}</Title><Badge text={u.STATUS} /></Row>
              <Muted>{`${u.DOC_TYPE} by ${u.UPLOADED_BY} - ${u.MESSAGE ?? ''}`}</Muted></Card>
          ))}
        </Section>
      ) : null}
    </View>
  );
}
