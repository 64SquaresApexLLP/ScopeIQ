// SharePoint upload. Pick one site, drop or choose files, upload. Files go only into the selected site's folder.
// Nothing selected -> "Please select one site" and no upload controls.
import * as DocumentPicker from 'expo-document-picker';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Platform, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { colors, shadow, space } from '../../components/theme';
import { Badge, Button, Card, Chips, ErrorView, Hero, Icon, IconBadge, Muted, s } from '../../components/ui';
import { api, ApiError } from '../../lib/api';
import { getLogger } from '../../lib/logger';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';

const log = getLogger('sharepoint');
const TYPES = [
  { key: 'AUTO', label: 'Auto-detect' }, { key: 'RFDS', label: 'RFDS' }, { key: 'CD', label: 'Drawing (CD)' }, { key: 'MA_SA', label: 'MA / SA' },
  { key: 'BOM_REV0', label: 'BOM REV 0' }, { key: 'DRONE_POINTCLOUD', label: 'Point cloud' }, { key: 'DRONE_VENDOR', label: 'Drone data' },
  { key: 'DRONE_IMAGE', label: 'Photo' }, { key: 'DRONE_VIDEO', label: 'Video' }, { key: 'DRONE_META', label: 'Metadata' },
] as const;
type T = (typeof TYPES)[number]['key'];
type Picked = { name: string; size?: number; uri: string; mimeType?: string; file?: File };
type Result = { name: string; ok: boolean; message: string };

const kb = (n?: number) => (!n ? '' : n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const fileIcon = (name: string) => (/\.(jpe?g|png|tif)$/i.test(name) ? 'image' : /\.(mp4|mov|avi)$/i.test(name) ? 'video' : /\.(xlsx|csv)$/i.test(name) ? 'grid' : /\.(laz|las)$/i.test(name) ? 'box' : 'file-text') as any;

function Step({ n, title, hint, children }: { n: number; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <Card style={{ padding: space(5) }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), marginBottom: space(4) }}>
        <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ color: '#fff', fontWeight: '800', fontSize: 13 }}>{n}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ fontSize: 16, fontWeight: '800', color: colors.text, letterSpacing: -0.3 }}>{title}</Text>
          {hint ? <Text style={{ fontSize: 12.5, color: colors.muted }}>{hint}</Text> : null}
        </View>
      </View>
      {children}
    </Card>
  );
}

export default function SharePoint() {
  const sites = useApi<{ location: string; sites: R[] }>('/sharepoint/sites');
  const [siteId, setSiteId] = useState<string | null>(null);
  const [type, setType] = useState<T>('AUTO');
  const [showType, setShowType] = useState(false);
  const [picked, setPicked] = useState<Picked[]>([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(0);
  const [results, setResults] = useState<Result[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [hover, setHover] = useState(false);
  const files = useApi<{ files: R[] }>(siteId ? `/sharepoint/sites/${siteId}/files` : null);
  const dropRef = useRef<any>(null);

  const selected = sites.data?.sites.find((x) => x.site_id === siteId) ?? null;
  const grouped = useMemo(() => {
    const g: Record<string, R[]> = {};
    for (const f of files.data?.files ?? []) (g[f.folder] ??= []).push(f);
    return g;
  }, [files.data]);

  const addFiles = (list: Picked[]) => { setPicked((p) => [...p, ...list.filter((n) => !p.some((o) => o.name === n.name))]); setResults([]); };

  useEffect(() => {      // drag and drop (web only)
    const el = dropRef.current as HTMLElement | null;
    if (Platform.OS !== 'web' || !el || !siteId) return;
    const over = (e: DragEvent) => { e.preventDefault(); setHover(true); };
    const leave = () => setHover(false);
    const drop = (e: DragEvent) => {
      e.preventDefault();
      setHover(false);
      addFiles(Array.from(e.dataTransfer?.files ?? []).map((f) => ({ name: f.name, size: f.size, uri: '', file: f })));
    };
    el.addEventListener('dragover', over); el.addEventListener('dragleave', leave); el.addEventListener('drop', drop);
    return () => { el.removeEventListener('dragover', over); el.removeEventListener('dragleave', leave); el.removeEventListener('drop', drop); };
  }, [siteId]);

  const choose = (id: string) => { setSiteId(id === siteId ? null : id); setPicked([]); setResults([]); setError(null); };

  const pick = async () => {
    const r = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, multiple: true });
    if (!r.canceled) addFiles(r.assets.map((a) => ({ name: a.name, size: a.size, uri: a.uri, mimeType: a.mimeType, file: a.file })));
  };

  const upload = async () => {
    if (!siteId || !picked.length) return;
    setBusy(true);
    setDone(0);
    setError(null);
    const out: Result[] = [];
    for (const f of picked) {
      try {
        const form = new FormData();
        if (type !== 'AUTO') form.append('doc_type', type);
        if (Platform.OS === 'web' && f.file) form.append('file', f.file, f.name);
        else form.append('file', { uri: f.uri, name: f.name, type: f.mimeType ?? 'application/octet-stream' } as unknown as Blob);
        const res = await api.upload<R>(`/sharepoint/sites/${siteId}/upload`, form);
        out.push({ name: f.name, ok: true, message: `Saved in ${res.folder}${res.replaced ? ' (replaced older file)' : ''}${res.duplicate_of ? ` - same content as ${res.duplicate_of}` : ''}` });
        log.info(`uploaded ${f.name} to ${siteId}/${res.folder}`);
      } catch (e) {
        out.push({ name: f.name, ok: false, message: (e as ApiError).message });
      }
      setDone((n) => n + 1);
    }
    setResults(out);
    setPicked([]);
    setBusy(false);
    files.reload();
    sites.reload();
  };

  const okCount = results.filter((r) => r.ok).length;

  return (
    <ScrollView style={s.screen} contentContainerStyle={[s.content, { maxWidth: 820, width: '100%', alignSelf: 'center' }]}
      refreshControl={<RefreshControl refreshing={sites.loading} onRefresh={sites.reload} />}>
      <Hero icon="upload-cloud" title="SharePoint documents" subtitle={sites.data?.location ?? 'Connecting...'} />
      {sites.error ? <ErrorView error={sites.error} onRetry={sites.reload} /> : null}

      <Step n={1} title="Choose a site" hint="Files are saved only in the folder of the site you pick.">
        {sites.data && sites.data.sites.length === 0 ? (
          <Muted>No sites yet. An administrator needs to create one first.</Muted>
        ) : (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(3) }}>
            {sites.data?.sites.map((x) => {
              const on = x.site_id === siteId;
              return (
                <Pressable key={x.site_id} onPress={() => choose(x.site_id)} accessibilityRole="button"
                  style={({ hovered }: any) => [{ flexGrow: 1, flexBasis: 220, flexDirection: 'row', alignItems: 'center', gap: space(3), padding: space(3.5), borderRadius: 14, borderWidth: 2, borderColor: on ? colors.accent : hovered ? '#C9D3F5' : colors.border, backgroundColor: on ? colors.soft : '#fff' }]}>
                  <IconBadge name="map-pin" color={on ? colors.accent : colors.muted} size={38} />
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: '800', color: colors.text, fontSize: 15 }}>{x.site_id}</Text>
                    <Text style={{ fontSize: 12.5, color: colors.muted }} numberOfLines={1}>{x.site_name || 'No name'}{x.city ? ` · ${x.city}` : ''}</Text>
                  </View>
                  {on ? <Icon name="check-circle" size={20} color={colors.accent} /> : <Badge text={`${x.files} file${x.files === 1 ? '' : 's'}`} color={colors.muted} />}
                </Pressable>
              );
            })}
          </View>
        )}
      </Step>

      {!siteId ? (
        sites.data && sites.data.sites.length > 0 ? (
          <View style={{ alignItems: 'center', padding: space(8), borderRadius: 16, backgroundColor: '#FFF8EB', borderWidth: 1, borderColor: '#F6DFB0' }}>
            <IconBadge name="mouse-pointer" color={colors.warn} size={48} />
            <Text style={{ marginTop: space(3), fontSize: 17, fontWeight: '800', color: colors.warn }}>Please select one site</Text>
            <Text style={{ marginTop: 4, color: '#8A6A2A', textAlign: 'center' }}>Pick a site above to start adding its documents.</Text>
          </View>
        ) : null
      ) : (
        <>
          <Step n={2} title={`Add files to ${siteId}`} hint={selected?.site_name ? `${selected.site_name}${selected.city ? ` · ${selected.city}, ${selected.state}` : ''}` : undefined}>
            <View ref={dropRef} style={{ borderWidth: 2, borderStyle: 'dashed', borderColor: hover ? colors.accent : '#CBD5E8', backgroundColor: hover ? colors.soft : '#F8FAFF', borderRadius: 16, paddingVertical: space(9), paddingHorizontal: space(4), alignItems: 'center', gap: space(2) }}>
              <IconBadge name="upload-cloud" color={colors.accent} size={56} />
              <Text style={{ fontSize: 17, fontWeight: '800', color: colors.text, marginTop: space(2) }}>{Platform.OS === 'web' ? 'Drag and drop files here' : 'Add your files'}</Text>
              <Text style={{ color: colors.muted, fontSize: 13 }}>RFDS, drawings, MA/SA, BOM, drone data, photos and video</Text>
              <View style={{ marginTop: space(3) }}><Button kind="secondary" title="Browse files" onPress={pick} /></View>
            </View>

            {picked.length > 0 ? (
              <View style={{ marginTop: space(4), borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' }}>
                {picked.map((f, i) => (
                  <View key={f.name} style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), padding: space(3), borderTopWidth: i ? 1 : 0, borderTopColor: colors.border }}>
                    <IconBadge name={fileIcon(f.name)} size={34} />
                    <Text style={{ flex: 1, color: colors.text, fontWeight: '600' }} numberOfLines={1}>{f.name}</Text>
                    <Muted>{kb(f.size)}</Muted>
                    <Pressable onPress={() => setPicked((p) => p.filter((x) => x.name !== f.name))} accessibilityLabel={`Remove ${f.name}`} style={{ padding: 4 }}>
                      <Icon name="x" size={16} />
                    </Pressable>
                  </View>
                ))}
              </View>
            ) : null}

            <Pressable onPress={() => setShowType((v) => !v)} style={{ marginTop: space(4), flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Icon name="sliders" size={14} color={colors.accent} />
              <Text style={{ color: colors.accent, fontSize: 13, fontWeight: '600' }}>Document type: {TYPES.find((t) => t.key === type)?.label}{type === 'AUTO' ? ' (from the file name)' : ''}</Text>
            </Pressable>
            {showType ? <Chips<T> value={type} onChange={setType} options={TYPES.map((t) => ({ key: t.key, label: t.label }))} /> : null}

            <View style={{ marginTop: space(5) }}>
              <Button title={busy ? `Uploading ${done}/${picked.length}...` : picked.length ? `Upload ${picked.length} file${picked.length === 1 ? '' : 's'} to ${siteId}` : `Upload to ${siteId}`} disabled={!picked.length || busy} onPress={upload} />
            </View>
            {error ? <ErrorView error={error} /> : null}

            {results.length > 0 ? (
              <View style={{ marginTop: space(5) }}>
                <Text style={{ fontWeight: '800', color: colors.text, marginBottom: space(2) }}>{okCount} of {results.length} uploaded</Text>
                {results.map((r) => (
                  <View key={r.name} style={{ flexDirection: 'row', gap: space(3), padding: space(3), marginBottom: space(2), borderRadius: 12, backgroundColor: r.ok ? '#F0FBF4' : '#FEF2F2', borderWidth: 1, borderColor: r.ok ? '#C6EBD3' : '#FAD0D0' }}>
                    <Icon name={r.ok ? 'check-circle' : 'x-circle'} size={20} color={r.ok ? colors.ok : colors.danger} />
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontWeight: '700', color: colors.text }}>{r.name}</Text>
                      <Text style={{ fontSize: 12.5, color: r.ok ? '#3C6B4E' : colors.danger }}>{r.message}</Text>
                    </View>
                  </View>
                ))}
              </View>
            ) : null}
          </Step>

          <Step n={3} title={`Documents in ${siteId}`} hint={files.data ? `${files.data.files.length} file${files.data.files.length === 1 ? '' : 's'}` : undefined}>
            {files.error ? <ErrorView error={files.error} onRetry={files.reload} /> : null}
            {files.data && files.data.files.length === 0 ? (
              <View style={{ alignItems: 'center', padding: space(4) }}><Icon name="folder" size={28} color="#B8C2D6" /><Muted style={{ marginTop: 6 }}>Nothing uploaded yet.</Muted></View>
            ) : null}
            {Object.entries(grouped).map(([folder, list], i) => (
              <View key={folder} style={{ marginTop: i ? space(4) : 0 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <Icon name="folder" size={15} color={colors.accent} />
                  <Text style={{ fontSize: 12, fontWeight: '800', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.8 }}>{folder}</Text>
                </View>
                {list.map((f) => (
                  <View key={folder + f.name} style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#EEF1F7' }}>
                    <Icon name={fileIcon(f.name)} size={16} color={colors.muted} />
                    <Text style={{ flex: 1, color: colors.text, fontSize: 13.5 }} numberOfLines={1}>{f.name}</Text>
                    <Muted>{kb(f.size)}</Muted>
                  </View>
                ))}
              </View>
            ))}
          </Step>
        </>
      )}
    </ScrollView>
  );
}
