// Optional artifact upload: pick the document type, pick the file, upload. The next pipeline run registers it;
// a newer revision (e.g. CD REV 2 from the A&E) supersedes the folder copy.
import * as DocumentPicker from 'expo-document-picker';
import { router, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { Platform, ScrollView, View } from 'react-native';
import { space } from '../../components/theme';
import { Button, Card, Chips, ErrorView, KV, Muted, Row, s, Title } from '../../components/ui';
import { api, ApiError } from '../../lib/api';
import { getLogger } from '../../lib/logger';
import { Row as R } from '../../lib/types';

const log = getLogger('upload');
const TYPES = [
  { key: 'CD', label: 'CD drawing', hint: 'SITE_CD_REV2.pdf / .dxf' }, { key: 'RFDS', label: 'RFDS', hint: 'SITE_RFDS_R4.xlsx / .pdf' },
  { key: 'MA_SA', label: 'MA / SA', hint: 'SITE_MA_SA.xlsx' }, { key: 'BOM_REV0', label: 'BOM REV 0', hint: 'SITE_BOM_REV0.xlsx' },
  { key: 'DRONE_VENDOR', label: 'Drone measurements', hint: 'vendor_measurements.csv' }, { key: 'DRONE_POINTCLOUD', label: 'Point cloud', hint: '.las / .laz' },
  { key: 'DRONE_IMAGE', label: 'Drone photo', hint: '.jpg / .png' }, { key: 'DRONE_VIDEO', label: 'Drone video', hint: '.mp4' },
  { key: 'DRONE_META', label: 'Capture metadata', hint: 'capture_metadata.json' },
] as const;
type T = (typeof TYPES)[number]['key'];

export default function Upload() {
  const { siteId } = useLocalSearchParams<{ siteId: string }>();
  const [type, setType] = useState<T>('CD');
  const [file, setFile] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const [done, setDone] = useState<R | null>(null);
  const [running, setRunning] = useState(false);

  const pick = async () => {
    const r = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, multiple: false });
    if (!r.canceled) {
      setFile(r.assets[0]);
      setDone(null);
      setErr(null);
    }
  };

  const send = async () => {
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const form = new FormData();
      form.append('doc_type', type);
      if (Platform.OS === 'web' && file.file) form.append('file', file.file, file.name);
      else form.append('file', { uri: file.uri, name: file.name, type: file.mimeType ?? 'application/octet-stream' } as unknown as Blob);
      const res = await api.upload<R>(`/sites/${siteId}/documents/upload`, form);
      setDone(res);
      log.info(`uploaded ${file.name} as ${type} for ${siteId}`);
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setBusy(false);
    }
  };

  const runPipeline = async () => {
    setRunning(true);
    try {
      await api.post(`/pipeline/sites/${siteId}/run`);
      router.back();
    } catch (e) {
      setErr(e as ApiError);
    } finally {
      setRunning(false);
    }
  };

  const hint = TYPES.find((t) => t.key === type)?.hint;
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content}>
      <Title>{`Upload to ${siteId}`}</Title>
      <Muted>Use the site naming convention so the revision is recognised, for example {`${siteId}_CD_REV2.pdf`}.</Muted>
      <Chips<T> value={type} onChange={setType} options={TYPES.map((t) => ({ key: t.key, label: t.label }))} />
      <Muted>{`Expected file: ${hint}`}</Muted>
      <View style={{ marginTop: space(3), gap: space(2) }}>
        <Button kind="secondary" title={file ? 'Choose a different file' : 'Choose file'} onPress={pick} />
        {file ? <Card><KV k="File" v={file.name} /><KV k="Size" v={file.size ? `${Math.round(file.size / 1024)} KB` : '-'} /></Card> : null}
        <Button title={busy ? 'Uploading...' : 'Upload'} disabled={!file || busy} onPress={send} />
        {err ? <ErrorView error={err} /> : null}
        {done ? (
          <Card>
            <Title>{done.STATUS === 'DUPLICATE' ? 'Uploaded (same content as an earlier upload)' : 'Uploaded'}</Title>
            <Muted>{done.MESSAGE}</Muted>
            <Row style={{ marginTop: space(2) }}><Button small title={running ? 'Running...' : 'Run pipeline now'} disabled={running} onPress={runPipeline} /></Row>
          </Card>
        ) : null}
      </View>
    </ScrollView>
  );
}
