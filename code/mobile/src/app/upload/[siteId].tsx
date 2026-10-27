// Optional artifact upload: pick the document type, pick the file, upload. The next pipeline run registers it;
// a newer revision (e.g. CD REV 2 from the A&E) supersedes the folder copy.
import * as DocumentPicker from 'expo-document-picker';
import { router, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { ActivityIndicator, Platform, Pressable, ScrollView, Text, View } from 'react-native';
import { colors, space } from '../../components/theme';
import { Badge, Button, Card, Chips, ErrorView, Icon, KV, Muted, Row, s, Title } from '../../components/ui';
import { api, ApiError } from '../../lib/api';
import { computeFileSha256 } from '../../lib/hash';
import { getLogger } from '../../lib/logger';
import { Row as R } from '../../lib/types';

const log = getLogger('upload');
const TYPES = [
  { key: 'CD', label: 'CD drawing', hint: 'SITE_CD_REV2.pdf / .dxf' },
  { key: 'RFDS', label: 'RFDS', hint: 'SITE_RFDS_R4.xlsx / .pdf' },
  { key: 'MA_SA', label: 'MA / SA', hint: 'SITE_MA_SA.xlsx' },
  { key: 'BOM_REV0', label: 'BOM REV 0', hint: 'SITE_BOM_REV0.xlsx' },
  { key: 'DRONE_VENDOR', label: 'Drone measurements', hint: 'vendor_measurements.csv' },
  { key: 'DRONE_POINTCLOUD', label: 'Point cloud', hint: '.las / .laz' },
  { key: 'DRONE_IMAGE', label: 'Drone photo', hint: '.jpg / .png' },
  { key: 'DRONE_VIDEO', label: 'Drone video', hint: '.mp4' },
  { key: 'DRONE_META', label: 'Capture metadata', hint: 'capture_metadata.json' },
] as const;
type T = (typeof TYPES)[number]['key'];

interface DiffInfo {
  summary?: string | null;
  added_count?: number;
  additions?: string[];
  total_additions?: number;
}

interface InspectionResult {
  status: 'NEW' | 'DUPLICATE' | 'UPDATED';
  isDuplicate: boolean;
  isUpdated: boolean;
  isNew: boolean;
  duplicateOf?: string | null;
  updatedFrom?: string | null;
  hash?: string | null;
  message?: string | null;
  warning?: string | null;
  diff?: DiffInfo | null;
}

export default function Upload() {
  const { siteId } = useLocalSearchParams<{ siteId: string }>();
  const [type, setType] = useState<T>('CD');
  const [file, setFile] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [hash, setHash] = useState<string | null>(null);
  const [hashing, setHashing] = useState(false);
  const [inspecting, setInspecting] = useState(false);
  const [inspection, setInspection] = useState<InspectionResult | null>(null);
  const [showAdditions, setShowAdditions] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null);
  const [done, setDone] = useState<R | null>(null);
  const [running, setRunning] = useState(false);

  const inspectFile = async (asset: DocumentPicker.DocumentPickerAsset, docType: T) => {
    setInspecting(true);
    setInspection(null);
    try {
      const form = new FormData();
      form.append('doc_type', docType);
      if (Platform.OS === 'web' && asset.file) {
        form.append('file', asset.file, asset.name);
      } else {
        form.append('file', { uri: asset.uri, name: asset.name, type: asset.mimeType ?? 'application/octet-stream' } as unknown as Blob);
      }

      const res = await api.upload<any>(`/sites/${siteId}/documents/check-content`, form);
      if (res) {
        setInspection({
          status: res.status,
          isDuplicate: res.status === 'DUPLICATE' || Boolean(res.is_duplicate),
          isUpdated: res.status === 'UPDATED' || Boolean(res.is_updated),
          isNew: res.status === 'NEW',
          duplicateOf: res.duplicate_of || res.existing_file,
          updatedFrom: res.updated_from || res.existing_file,
          hash: res.file_hash,
          message: res.message,
          warning: res.warning,
          diff: res.diff,
        });
      }
    } catch {
      // Pre-check network error ignored; backend will still enforce content check on upload
    } finally {
      setInspecting(false);
    }
  };

  const pick = async () => {
    const r = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, multiple: false });
    if (!r.canceled) {
      const asset = r.assets[0];
      setFile(asset);
      setDone(null);
      setErr(null);
      setHashing(true);

      const computedHash = await computeFileSha256(asset);
      setHash(computedHash);
      setHashing(false);

      await inspectFile(asset, type);
    }
  };

  const onTypeChange = (newType: T) => {
    setType(newType);
    if (file) {
      inspectFile(file, newType);
    }
  };

  const send = async (options?: {
    replace?: boolean;
    targetFile?: string;
    confirmDuplicate?: boolean;
    confirmUpdate?: boolean;
  }) => {
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const form = new FormData();
      form.append('doc_type', type);

      if (options?.replace) {
        form.append('action', 'REPLACE');
        if (options.targetFile) {
          form.append('replace_file', options.targetFile);
        }
      }
      if (options?.confirmDuplicate) {
        form.append('confirm_duplicate', 'true');
      }
      if (options?.confirmUpdate) {
        form.append('confirm_update', 'true');
      }

      if (Platform.OS === 'web' && file.file) {
        form.append('file', file.file, file.name);
      } else {
        form.append('file', { uri: file.uri, name: file.name, type: file.mimeType ?? 'application/octet-stream' } as unknown as Blob);
      }

      const res = await api.upload<R>(`/sites/${siteId}/documents/upload`, form);
      setDone(res);
      setInspection(null);
      log.info(`uploaded ${file.name} as ${type} for ${siteId}`);
    } catch (e: any) {
      const apiErr = e as ApiError;
      if (apiErr.status === 409 && (apiErr.details?.is_duplicate || apiErr.details?.is_updated)) {
        setInspection({
          status: apiErr.details.status || (apiErr.details.is_duplicate ? 'DUPLICATE' : 'UPDATED'),
          isDuplicate: Boolean(apiErr.details.is_duplicate),
          isUpdated: Boolean(apiErr.details.is_updated),
          isNew: false,
          duplicateOf: apiErr.details.duplicate_of,
          updatedFrom: apiErr.details.updated_from,
          hash: apiErr.details.file_hash || hash,
          message: apiErr.details.message || apiErr.message,
          warning: apiErr.details.warning,
          diff: apiErr.details.diff,
        });
      } else {
        setErr(apiErr);
      }
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
      <Chips<T> value={type} onChange={onTypeChange} options={TYPES.map((t) => ({ key: t.key, label: t.label }))} />
      <Muted>{`Expected file: ${hint}`}</Muted>

      <View style={{ marginTop: space(3), gap: space(3) }}>
        <Button kind="secondary" title={file ? 'Choose a different file' : 'Choose file'} onPress={pick} />

        {file ? (
          <Card>
            <KV k="File" v={file.name} />
            <KV k="Size" v={file.size ? `${Math.round(file.size / 1024)} KB` : '-'} />
            <KV
              k="Data Check"
              v={
                inspecting || hashing ? (
                  <Row style={{ gap: space(2), alignItems: 'center' }}>
                    <ActivityIndicator size="small" color={colors.accent} />
                    <Text style={{ fontSize: 12, color: colors.muted }}>Checking content & duplicate data...</Text>
                  </Row>
                ) : inspection?.isDuplicate ? (
                  <Row style={{ gap: space(1.5), alignItems: 'center' }}>
                    <Icon name="alert-triangle" size={14} color="#D97706" />
                    <Text style={{ fontSize: 12, fontWeight: '700', color: '#D97706' }}>Already Exists</Text>
                  </Row>
                ) : inspection?.isUpdated ? (
                  <Row style={{ gap: space(1.5), alignItems: 'center' }}>
                    <Icon name="file-text" size={14} color="#2563EB" />
                    <Text style={{ fontSize: 12, fontWeight: '700', color: '#2563EB' }}>
                      {inspection.diff?.added_count ? `Changes Detected (+${inspection.diff.added_count})` : 'Changes Detected'}
                    </Text>
                  </Row>
                ) : (
                  <Row style={{ gap: space(1.5), alignItems: 'center' }}>
                    <Icon name="check-circle" size={14} color={colors.ok} />
                    <Text style={{ fontSize: 12, fontWeight: '700', color: colors.ok }}>New Data Verified</Text>
                  </Row>
                )
              }
            />
            {hash ? (
              <KV
                k="SHA-256 Hash"
                v={<Text style={{ fontFamily: 'monospace', fontSize: 11, color: colors.muted }}>{`${hash.slice(0, 16)}...`}</Text>}
              />
            ) : null}
          </Card>
        ) : null}

        {/* 1. SAME DATA DETECTED -> "ALREADY EXISTS" MESSAGE (NO REPLACE FILE OPTION) */}
        {inspection?.isDuplicate ? (
          <View
            style={{
              backgroundColor: '#FFFBEB',
              borderWidth: 1.5,
              borderColor: '#F59E0B',
              borderRadius: 12,
              padding: space(4),
              gap: space(3),
            }}
          >
            <Row style={{ gap: space(2), alignItems: 'center' }}>
              <Icon name="alert-triangle" size={24} color="#D97706" />
              <View style={{ flex: 1 }}>
                <Text style={{ fontWeight: '800', color: '#92400E', fontSize: 16 }}>Already Exists</Text>
                <Text style={{ color: '#B45309', fontSize: 12.5, marginTop: 2 }}>
                  File with identical data already exists on this site
                </Text>
              </View>
            </Row>

            <Text style={{ color: '#B45309', fontSize: 13.5, lineHeight: 19 }}>
              This file already exists. The data inside matches existing file{' '}
              <Text style={{ fontWeight: '800', color: '#78350F' }}>
                {inspection.duplicateOf || 'an existing file'}
              </Text>{' '}
              on this site. Upload is not required because no new data was detected.
            </Text>

            <View
              style={{
                backgroundColor: '#FEF3C7',
                padding: space(3),
                borderRadius: 8,
                borderWidth: 1,
                borderColor: '#FDE68A',
              }}
            >
              <Text style={{ fontSize: 13.5, fontWeight: '700', color: '#78350F' }}>
                File already exists. No changes found to replace.
              </Text>
            </View>

            <Row style={{ gap: space(2.5), flexWrap: 'wrap', marginTop: space(1) }}>
              <Button
                kind="secondary"
                title="Choose a different file"
                onPress={pick}
              />
            </Row>
          </View>
        ) : null}

        {/* 2. SAME FILE WITH CHANGES DETECTED -> SHOW REPLACE FILE OPTION */}
        {inspection?.isUpdated ? (
          <View
            style={{
              backgroundColor: '#EFF6FF',
              borderWidth: 1.5,
              borderColor: '#3B82F6',
              borderRadius: 12,
              padding: space(4),
              gap: space(3),
            }}
          >
            <Row style={{ gap: space(2), alignItems: 'center' }}>
              <Icon name="file-text" size={24} color="#2563EB" />
              <View style={{ flex: 1 }}>
                <Row style={{ gap: space(2), alignItems: 'center' }}>
                  <Text style={{ fontWeight: '800', color: '#1E40AF', fontSize: 16 }}>Changes Detected</Text>
                  {inspection.diff?.added_count ? (
                    <Badge text={`${inspection.diff.added_count} change${inspection.diff.added_count > 1 ? 's' : ''}`} color="#2563EB" />
                  ) : null}
                </Row>
                <Text style={{ color: '#3B82F6', fontSize: 12.5, marginTop: 2 }}>
                  File contains changes compared to {inspection.updatedFrom || 'the existing file'}
                </Text>
              </View>
            </Row>

            <Text style={{ color: '#1E3A8A', fontSize: 13.5, lineHeight: 19 }}>
              This file contains changes compared to existing file{' '}
              <Text style={{ fontWeight: '800', color: '#172554' }}>
                {inspection.updatedFrom || 'an existing file'}
              </Text>.
            </Text>

            {/* Prompt Question */}
            <View
              style={{
                backgroundColor: '#DBEAFE',
                padding: space(3),
                borderRadius: 8,
                borderWidth: 1,
                borderColor: '#BFDBFE',
              }}
            >
              <Text style={{ fontSize: 13.5, fontWeight: '700', color: '#1E3A8A' }}>
                Do you want to replace the existing file with this updated file?
              </Text>
            </View>

            {/* What is new / changed section */}
            <View style={{ marginTop: space(1) }}>
              <Pressable
                onPress={() => setShowAdditions(!showAdditions)}
                style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: space(1.5) }}
              >
                <Row style={{ gap: space(1.5), alignItems: 'center' }}>
                  <Icon name="layers" size={16} color="#2563EB" />
                  <Text style={{ fontWeight: '800', fontSize: 13.5, color: '#1E40AF' }}>
                    What is changed in this file:
                  </Text>
                </Row>
                <Text style={{ fontSize: 12, color: '#3B82F6', fontWeight: '700' }}>
                  {showAdditions ? 'Hide changes ▲' : `Show ${inspection.diff?.added_count ?? ''} changes ▼`}
                </Text>
              </Pressable>

              {showAdditions && inspection.diff?.additions?.length ? (
                <View
                  style={{
                    maxHeight: 180,
                    backgroundColor: '#FFFFFF',
                    borderRadius: 8,
                    borderWidth: 1,
                    borderColor: '#BFDBFE',
                    padding: space(2.5),
                  }}
                >
                  <ScrollView nestedScrollEnabled>
                    {inspection.diff.additions.map((item, idx) => (
                      <View
                        key={idx}
                        style={{
                          flexDirection: 'row',
                          alignItems: 'flex-start',
                          gap: space(2),
                          paddingVertical: 5,
                          borderBottomWidth: idx < (inspection.diff?.additions?.length ?? 0) - 1 ? 0.5 : 0,
                          borderBottomColor: '#E2E8F0',
                        }}
                      >
                        <View
                          style={{
                            backgroundColor: '#DBEAFE',
                            borderRadius: 4,
                            paddingHorizontal: 6,
                            paddingVertical: 2,
                            marginTop: 1,
                          }}
                        >
                          <Text style={{ fontSize: 10, fontWeight: '800', color: '#1D4ED8' }}>DIFF</Text>
                        </View>
                        <Text style={{ flex: 1, fontSize: 12, fontFamily: 'monospace', color: '#1E293B', lineHeight: 18 }}>
                          {item}
                        </Text>
                      </View>
                    ))}
                  </ScrollView>
                </View>
              ) : null}
            </View>

            <Row style={{ gap: space(2.5), flexWrap: 'wrap', marginTop: space(1) }}>
              <Button
                title={busy ? 'Replacing...' : 'Replace Existing File'}
                disabled={busy}
                onPress={() => send({ replace: true, targetFile: inspection.updatedFrom || undefined })}
              />
              <Button
                kind="secondary"
                title={busy ? 'Uploading...' : 'Keep Both (Upload as New Version)'}
                disabled={busy}
                onPress={() => send({ confirmUpdate: true })}
              />
            </Row>
          </View>
        ) : null}

        {/* 3. BRAND NEW DATA CONFIRMATION BADGE */}
        {inspection?.isNew ? (
          <View
            style={{
              backgroundColor: '#F0FDF4',
              borderWidth: 1.5,
              borderColor: '#86EFAC',
              borderRadius: 12,
              padding: space(3.5),
              gap: space(1.5),
            }}
          >
            <Row style={{ gap: space(2), alignItems: 'center' }}>
              <Icon name="check-circle" size={20} color={colors.ok} />
              <Text style={{ fontWeight: '800', color: '#166534', fontSize: 14 }}>New Document Data</Text>
            </Row>
            <Text style={{ fontSize: 13, color: '#15803D' }}>
              No existing duplicates or previous versions detected for this site. Ready to store.
            </Text>
          </View>
        ) : null}

        {/* Standard Upload button when file is picked and not blocked by duplicate/updated prompts */}
        {!inspection?.isDuplicate && !inspection?.isUpdated ? (
          <Button
            title={busy ? 'Uploading...' : inspecting ? 'Checking file...' : 'Upload Document'}
            disabled={!file || busy || inspecting}
            onPress={() => send()}
          />
        ) : null}

        {err ? <ErrorView error={err} /> : null}

        {/* 4. SUCCESS RESULT CARD */}
        {done ? (
          <Card
            style={
              done.replaced
                ? { backgroundColor: '#F0FDF4', borderColor: '#22C55E', borderWidth: 1.5 }
                : done.STATUS === 'DUPLICATE' || done.is_duplicate
                ? { backgroundColor: '#FFFBEB', borderColor: '#F59E0B', borderWidth: 1.5 }
                : done.is_updated
                ? { backgroundColor: '#EFF6FF', borderColor: '#3B82F6', borderWidth: 1.5 }
                : undefined
            }
          >
            <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <Row style={{ gap: space(2), alignItems: 'center' }}>
                <Icon
                  name={
                    done.replaced || done.STATUS === 'RECEIVED'
                      ? 'check-circle'
                      : done.STATUS === 'DUPLICATE'
                      ? 'alert-triangle'
                      : 'file-text'
                  }
                  size={22}
                  color={
                    done.replaced || done.STATUS === 'RECEIVED'
                      ? colors.ok
                      : done.STATUS === 'DUPLICATE'
                      ? colors.warn
                      : colors.accent
                  }
                />
                <Title>
                  {done.replaced
                    ? `Successfully Replaced ${done.replaced_file || 'Existing File'}`
                    : done.STATUS === 'DUPLICATE' || done.is_duplicate
                    ? 'Uploaded as Duplicate'
                    : done.is_updated
                    ? 'Uploaded Updated Version'
                    : 'Uploaded Successfully'}
                </Title>
              </Row>
              <Badge text={done.replaced ? 'REPLACED' : done.STATUS} />
            </Row>

            <Muted style={{ marginTop: space(2) }}>{done.MESSAGE}</Muted>

            {done.diff?.summary ? (
              <Text style={{ fontSize: 12, color: '#2563EB', marginTop: space(1), fontWeight: '600' }}>
                {`Additions: ${done.diff.summary}`}
              </Text>
            ) : null}

            {done.FILE_HASH ? (
              <Text style={{ fontSize: 11, fontFamily: 'monospace', color: colors.muted, marginTop: space(1) }}>
                SHA-256: {done.FILE_HASH}
              </Text>
            ) : null}

            <Row style={{ marginTop: space(3) }}>
              <Button small title={running ? 'Running...' : 'Run pipeline now'} disabled={running} onPress={runPipeline} />
            </Row>
          </Card>
        ) : null}
      </View>
    </ScrollView>
  );
}
