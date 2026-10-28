// SharePoint upload. Pick one site, drop or choose files, upload. Files go only into the selected site's folder.
// Nothing selected -> "Please select one site" and no upload controls.
import * as DocumentPicker from 'expo-document-picker';
import { useFocusEffect } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Platform, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { colors, shadow, space } from '../../components/theme';
import { Badge, Button, Card, Chips, ErrorView, Hero, Icon, IconBadge, Muted, Row, s } from '../../components/ui';
import { api, ApiError } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { computeFileSha256 } from '../../lib/hash';
import { getLogger } from '../../lib/logger';
import { Row as R } from '../../lib/types';
import { mutateApi, useApi } from '../../lib/useApi';

const log = getLogger('sharepoint');
const TYPES = [
  { key: 'AUTO', label: 'Auto-detect' }, { key: 'RFDS', label: 'RFDS' }, { key: 'CD', label: 'Drawing (CD)' }, { key: 'MA_SA', label: 'MA / SA' },
  { key: 'BOM_REV0', label: 'BOM REV 0' }, { key: 'DRONE_POINTCLOUD', label: 'Point cloud' }, { key: 'DRONE_VENDOR', label: 'Drone data' },
  { key: 'DRONE_IMAGE', label: 'Photo' }, { key: 'DRONE_VIDEO', label: 'Video' }, { key: 'DRONE_META', label: 'Metadata' },
] as const;
type T = (typeof TYPES)[number]['key'];
type Picked = {
  name: string;
  size?: number;
  uri: string;
  mimeType?: string;
  file?: File;
  hash?: string | null;
  duplicateOf?: string | null;
  isDuplicate?: boolean;
  isUpdated?: boolean;
  updatedFrom?: string | null;
  diffSummary?: string | null;
  additions?: string[];
  replace?: boolean;
  notAllowedForAe?: boolean;
  notAllowedReason?: string | null;
};
type Result = {
  name: string;
  ok: boolean;
  message: string;
  isDuplicate?: boolean;
  duplicateOf?: string | null;
  isUpdated?: boolean;
  updatedFrom?: string | null;
  replaced?: boolean;
  hash?: string | null;
};

function classifyFileName(name: string): string | null {
  if (/(?:_|-|\b)RFDS(?:_|-|\.|\b)/i.test(name) || /RFDS/i.test(name)) return 'RFDS';
  if (/(?:^|[-_\s])(?:CD|PCD)(?:[-_\s.]|$)/i.test(name)) return 'CD';
  if (/(?:^|[-_\s])(?:SAMA|MA_SA|SA_MA|MA|SA)(?:[-_\s.]|$)/i.test(name)) return 'MA_SA';
  if (/BOM/i.test(name)) return 'BOM_REV0';
  if (/capture_metadata\.json$/i.test(name)) return 'DRONE_META';
  if (/vendor_measurements\.csv$/i.test(name)) return 'DRONE_VENDOR';
  if (/\.la[sz]$/i.test(name)) return 'DRONE_POINTCLOUD';
  if (/\.(jpe?g|png|tif)$/i.test(name)) return 'DRONE_IMAGE';
  if (/\.(mp4|mov|avi)$/i.test(name)) return 'DRONE_VIDEO';
  return null;
}

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
  const { user, can } = useAuth();
  const isAdmin = user?.role === 'ADMIN' || can('ADMIN');
  const isAe = user?.role === 'AE_ENGINEER';
  const canUseSharePoint = isAdmin || isAe;
  const sites = useApi<{ location: string; sites: R[] }>(canUseSharePoint ? '/sharepoint/sites' : null);
  const firstFocus = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (firstFocus.current) {
        firstFocus.current = false;
        return;
      }
      if (canUseSharePoint) {
        sites.reload(true);
      }
    }, [canUseSharePoint, sites.reload]),
  );
  const [siteId, setSiteId] = useState<string | null>(null);
  const [type, setType] = useState<T>('AUTO');
  const [showType, setShowType] = useState(false);
  const [picked, setPicked] = useState<Picked[]>([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(0);
  const [results, setResults] = useState<Result[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [hover, setHover] = useState(false);
  const files = useApi<{ files: R[] }>(canUseSharePoint && siteId ? `/sharepoint/sites/${siteId}/files` : null);
  const dropRef = useRef<any>(null);

  if (!canUseSharePoint) {
    return (
      <View style={[s.screen, { alignItems: 'center', justifyContent: 'center', padding: space(8) }]}>
        <IconBadge name="lock" color={colors.muted} size={56} />
        <Text style={{ fontWeight: '800', fontSize: 18, color: colors.text, marginTop: space(3) }}>Administrators only</Text>
        <Muted>SharePoint document library access is restricted to administrators only and is not accessible to Scopers.</Muted>
      </View>
    );
  }

  const selected = sites.data?.sites.find((x) => x.site_id === siteId) ?? null;
  const grouped = useMemo(() => {
    const g: Record<string, R[]> = {};
    for (const f of files.data?.files ?? []) (g[f.folder] ??= []).push(f);
    return g;
  }, [files.data]);

  const addFiles = async (list: Picked[]) => {
    const existing = files.data?.files ?? [];
    const enriched: Picked[] = await Promise.all(
      list.map(async (item) => {
        // If user is A&E Engineer, verify file type is allowed (strictly CD or MA_SA / SA_MA)
        // Admin is NEVER restricted and can upload any file type (RFDS, BOM, CD, SAMA, DRONE, etc.)
        const detectedType = classifyFileName(item.name);
        const effectiveType = type !== 'AUTO' ? type : detectedType;
        const isAllowedForAe = (detectedType === 'CD' || detectedType === 'MA_SA') || (!detectedType && (effectiveType === 'CD' || effectiveType === 'MA_SA'));
        const isRestrictedForAe = isAe && !isAllowedForAe;

        if (isRestrictedForAe) {
          return {
            ...item,
            hash: null,
            isDuplicate: false,
            duplicateOf: null,
            isUpdated: false,
            updatedFrom: null,
            diffSummary: null,
            additions: [],
            replace: false,
            notAllowedForAe: true,
            notAllowedReason: `A&E Engineers can only upload CD and SA_MA documents. "${item.name}" is ${detectedType ? `a ${detectedType}` : 'not a CD or SA_MA'} document.`,
          };
        }

        const hash = await computeFileSha256(item);
        const match = hash ? existing.find((ef: any) => ef.hash === hash) : null;
        const nameMatch = existing.find((ef: any) => ef.name?.toLowerCase() === item.name?.toLowerCase());

        // 1. Exact hash match -> identical duplicate (Already exists)
        // 2. Same filename but DIFFERENT hash -> updated (Changes detected)
        // 3. Otherwise -> new file
        let isDup = Boolean(match);
        let dupOf = match ? (match.name as string) : null;
        let isUpd = Boolean(!match && nameMatch);
        let updFrom = !match && nameMatch ? (nameMatch.name as string) : null;
        let diffSum: string | null = null;
        let additionsList: string[] = [];

        if (siteId) {
          try {
            const form = new FormData();
            const fileDocType = type !== 'AUTO' ? type : isAe ? detectedType : undefined;
            if (fileDocType) form.append('doc_type', fileDocType);
            if (Platform.OS === 'web' && item.file) form.append('file', item.file, item.name);
            else form.append('file', { uri: item.uri, name: item.name, type: item.mimeType ?? 'application/octet-stream' } as unknown as Blob);
            const insp = await api.upload<any>(`/sharepoint/sites/${siteId}/check-content`, form);
            if (insp) {
              if (insp.status === 'DUPLICATE') {
                isDup = true;
                dupOf = insp.duplicate_of || insp.existing_file || dupOf || item.name;
                isUpd = false;
                updFrom = null;
                diffSum = null;
                additionsList = [];
              } else if (insp.status === 'UPDATED') {
                isUpd = true;
                isDup = false;
                dupOf = null;
                updFrom = insp.updated_from || insp.existing_file || updFrom || item.name;
                diffSum = insp.diff?.summary;
                additionsList = insp.diff?.additions || [];
              } else if (insp.status === 'NEW') {
                isDup = false;
                dupOf = null;
                isUpd = false;
                updFrom = null;
                diffSum = null;
                additionsList = [];
              }
            }
          } catch {}
        }

        return {
          ...item,
          hash,
          isDuplicate: isDup && !isUpd,
          duplicateOf: isDup && !isUpd ? dupOf : null,
          isUpdated: isUpd && !isDup,
          updatedFrom: isUpd && !isDup ? updFrom : null,
          diffSummary: isUpd && !isDup ? diffSum : null,
          additions: isUpd && !isDup ? additionsList : [],
          replace: isUpd && !isDup, // Default to true if updated; user can toggle to keep both files
          notAllowedForAe: false,
          notAllowedReason: null,
        };
      })
    );
    setPicked(enriched);
    setResults([]);
    setError(null);
  };

  useEffect(() => {      // drag and drop (web only)
    const el = dropRef.current as HTMLElement | null;
    if (Platform.OS !== 'web' || !el || !siteId) return;
    const over = (e: DragEvent) => { e.preventDefault(); setHover(true); };
    const leave = () => setHover(false);
    const drop = (e: DragEvent) => {
      e.preventDefault();
      setHover(false);
      setResults([]);
      setError(null);
      addFiles(Array.from(e.dataTransfer?.files ?? []).map((f) => ({ name: f.name, size: f.size, uri: '', file: f })));
    };
    el.addEventListener('dragover', over); el.addEventListener('dragleave', leave); el.addEventListener('drop', drop);
    return () => { el.removeEventListener('dragover', over); el.removeEventListener('dragleave', leave); el.removeEventListener('drop', drop); };
  }, [siteId, files.data]);

  const choose = (id: string) => { setSiteId(id === siteId ? null : id); setPicked([]); setResults([]); setError(null); };

  const pick = async () => {
    const r = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true, multiple: true });
    if (!r.canceled) {
      setResults([]);
      setError(null);
      addFiles(r.assets.map((a) => ({ name: a.name, size: a.size, uri: a.uri, mimeType: a.mimeType, file: a.file })));
    }
  };

  const uploadableFiles = picked.filter((f) => !f.isDuplicate && !f.notAllowedForAe);
  const allBlocked = picked.length > 0 && uploadableFiles.length === 0;

  const upload = async () => {
    if (!siteId || !picked.length) return;
    setBusy(true);
    setDone(0);
    setError(null);
    const out: Result[] = [];
    for (const f of picked) {
      if (f.notAllowedForAe) {
        out.push({
          name: f.name,
          ok: false,
          message: f.notAllowedReason || 'Upload blocked: A&E Engineers can only upload CD and MA/SA documents.',
        });
        setDone((n) => n + 1);
        continue;
      }
      if (f.isDuplicate) {
        // Do NOT upload same/duplicate file to the site
        out.push({
          name: f.name,
          ok: false,
          isDuplicate: true,
          duplicateOf: f.duplicateOf || undefined,
          hash: f.hash,
          message: `Upload blocked: Same file already exists on this site ("${f.duplicateOf || f.name}").`,
        });
        setDone((n) => n + 1);
        continue;
      }
      try {
        const form = new FormData();
        const fileDocType = type !== 'AUTO' ? type : isAe ? (classifyFileName(f.name) || 'CD') : undefined;
        if (fileDocType) form.append('doc_type', fileDocType);
        if (f.replace) {
          form.append('action', 'REPLACE');
          const target = f.updatedFrom || f.duplicateOf;
          if (target) form.append('replace_file', target);
        }
        if (Platform.OS === 'web' && f.file) form.append('file', f.file, f.name);
        else form.append('file', { uri: f.uri, name: f.name, type: f.mimeType ?? 'application/octet-stream' } as unknown as Blob);
        const res = await api.upload<R>(`/sharepoint/sites/${siteId}/upload`, form);
        const dupName = (res.duplicate_of as string) || f.duplicateOf;
        const isDup = Boolean(dupName || res.is_duplicate);
        const isUpd = Boolean(res.is_updated || f.isUpdated);
        const updName = (res.updated_from as string) || f.updatedFrom;
        const wasReplaced = Boolean(res.replaced || f.replace);
        const hashVal = (res.hash as string) || f.hash;

        let msg = `Saved in ${res.folder}`;
        if (wasReplaced) {
          msg = `Replaced existing file "${updName || dupName || f.name}" in ${res.folder}`;
        } else if (isDup) {
          msg = `Already exists: File with identical data already exists as "${dupName}".`;
        } else if (isUpd) {
          msg = `Updated document saved in ${res.folder} (based on ${updName})`;
        }

        out.push({
          name: f.name,
          ok: true,
          isDuplicate: isDup && !isUpd,
          duplicateOf: isDup && !isUpd ? dupName : null,
          isUpdated: isUpd && !isDup,
          updatedFrom: isUpd && !isDup ? updName : null,
          replaced: wasReplaced,
          hash: hashVal,
          message: msg,
        });
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
    mutateApi('/sites');
  };

  const okCount = results.filter((r) => r.ok).length;
  const dupCount = results.filter((r) => r.isDuplicate).length;

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
              <Text style={{ color: colors.muted, fontSize: 13 }}>{isAe ? 'CD drawings and SA_MA reports' : 'RFDS, drawings, MA/SA, BOM, drone data, photos and video'}</Text>
              <View style={{ marginTop: space(3) }}><Button kind="secondary" title="Browse files" onPress={pick} /></View>
            </View>

            {picked.length > 0 ? (
              <View style={{ marginTop: space(4), borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' }}>
                {picked.map((f, i) => {
                  const isBlockedAe = Boolean(f.notAllowedForAe);
                  const isDup = !isBlockedAe && Boolean(f.isDuplicate && !f.isUpdated);
                  const isUpd = !isBlockedAe && Boolean(f.isUpdated && !f.isDuplicate);
                  return (
                    <View
                      key={f.name}
                      style={{
                        padding: space(3.5),
                        borderTopWidth: i ? 1 : 0,
                        borderTopColor: colors.border,
                        backgroundColor: isBlockedAe || isDup ? '#FFFBEB' : isUpd ? '#EFF6FF' : '#FFFFFF',
                        gap: space(2),
                      }}
                    >
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3) }}>
                        <IconBadge name={fileIcon(f.name)} size={34} color={isBlockedAe || isDup ? colors.danger : isUpd ? '#2563EB' : undefined} />
                        <View style={{ flex: 1 }}>
                          <Row style={{ alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
                            <Text style={{ color: colors.text, fontWeight: '700' }} numberOfLines={1}>
                              {f.name}
                            </Text>
                            {isBlockedAe ? <Badge text="A&E RESTRICTED · WILL NOT UPLOAD" color={colors.danger} /> : null}
                            {isDup ? <Badge text="ALREADY EXISTS · WILL NOT UPLOAD" color={colors.danger} /> : null}
                            {isUpd ? <Badge text="CHANGES DETECTED" color="#2563EB" /> : null}
                          </Row>
                          {isBlockedAe ? (
                            <Text style={{ fontSize: 12, color: colors.danger, fontWeight: '600', marginTop: 2 }}>
                              ⚠️ {f.notAllowedReason || 'A&E Engineers can only upload CD and SA_MA documents.'}
                            </Text>
                          ) : isDup ? (
                            <Text style={{ fontSize: 12, color: colors.danger, fontWeight: '600', marginTop: 2 }}>
                              ⚠️ File already exists with identical data (matches &quot;{f.duplicateOf || f.name}&quot;) — upload blocked
                            </Text>
                          ) : isUpd ? (
                            <Text style={{ fontSize: 12, color: '#1E40AF', fontWeight: '600', marginTop: 2 }}>
                              ✨ Changes detected compared to &quot;{f.updatedFrom || f.name}&quot; ({f.diffSummary || 'modified content'})
                            </Text>
                          ) : f.hash ? (
                            <Text style={{ fontSize: 11, fontFamily: 'monospace', color: colors.muted, marginTop: 2 }}>
                              SHA-256: {f.hash.slice(0, 16)}...
                            </Text>
                          ) : null}
                        </View>
                        <Muted>{kb(f.size)}</Muted>
                        <Pressable onPress={() => setPicked((p) => p.filter((x) => x.name !== f.name))} accessibilityLabel={`Remove ${f.name}`} style={{ padding: 4 }}>
                          <Icon name="x" size={16} />
                        </Pressable>
                      </View>

                      {/* A&E Restricted banner */}
                      {isBlockedAe ? (
                        <View
                          style={{
                            backgroundColor: '#FEF2F2',
                            borderWidth: 1,
                            borderColor: '#FECACA',
                            padding: space(2.5),
                            borderRadius: 8,
                            marginTop: space(1),
                          }}
                        >
                          <Text style={{ fontSize: 12, fontWeight: '700', color: '#B91C1C' }}>
                            A&E Engineers are only permitted to upload CD and SA_MA documents for this site.
                          </Text>
                        </View>
                      ) : null}

                      {/* Same data detected: Already exists banner - NO replace option */}
                      {isDup ? (
                        <View
                          style={{
                            backgroundColor: '#FEF2F2',
                            borderWidth: 1,
                            borderColor: '#FECACA',
                            padding: space(2.5),
                            borderRadius: 8,
                            marginTop: space(1),
                          }}
                        >
                          <Text style={{ fontSize: 12, fontWeight: '700', color: '#B91C1C' }}>
                            File already exists on this site. Same file will not be uploaded.
                          </Text>
                        </View>
                      ) : null}

                      {/* Changes detected: Replace or keep both files choice prompt ONLY for files with changes */}
                      {isUpd ? (
                        <Pressable
                          onPress={() => setPicked((p) => p.map((x) => (x.name === f.name ? { ...x, replace: !x.replace } : x)))}
                          style={{
                            flexDirection: 'row',
                            alignItems: 'center',
                            gap: space(2.5),
                            backgroundColor: f.replace ? '#DBEAFE' : '#F8FAFC',
                            padding: space(2.5),
                            borderRadius: 8,
                            marginTop: space(1),
                            borderWidth: 1.5,
                            borderColor: f.replace ? '#60A5FA' : '#CBD5E1',
                          }}
                        >
                          <View
                            style={{
                              width: 20,
                              height: 20,
                              borderRadius: 5,
                              borderWidth: 1.5,
                              borderColor: f.replace ? '#2563EB' : colors.muted,
                              backgroundColor: f.replace ? '#2563EB' : '#FFFFFF',
                              alignItems: 'center',
                              justifyContent: 'center',
                            }}
                          >
                            {f.replace ? <Icon name="check" size={14} color="#FFFFFF" /> : null}
                          </View>
                          <View style={{ flex: 1 }}>
                            <Text style={{ fontSize: 12.5, fontWeight: '700', color: f.replace ? '#1E40AF' : colors.text }}>
                              {f.replace
                                ? `Replace existing file "${f.updatedFrom || f.name}" with this updated file`
                                : `Keep both files (save as new file alongside "${f.updatedFrom || f.name}")`}
                            </Text>
                            <Text style={{ fontSize: 11, color: colors.muted, marginTop: 2 }}>
                              {f.replace ? 'Checked: existing file will be replaced. Click to uncheck and keep both files.' : 'Unchecked: both files will be kept. Click to replace existing file.'}
                            </Text>
                          </View>
                        </Pressable>
                      ) : null}
                    </View>
                  );
                })}
              </View>
            ) : null}

            <Pressable onPress={() => setShowType((v) => !v)} style={{ marginTop: space(4), flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Icon name="sliders" size={14} color={colors.accent} />
              <Text style={{ color: colors.accent, fontSize: 13, fontWeight: '600' }}>
                Document type: {isAe ? 'Auto-detect (CD/SA_MA)' : `${TYPES.find((t) => t.key === type)?.label}${type === 'AUTO' ? ' (from the file name)' : ''}`}
              </Text>
            </Pressable>
            {showType || isAe ? (
              <View style={{ marginTop: space(2) }}>
                <Chips<T>
                  value={type}
                  onChange={setType}
                  options={TYPES
                    .filter((t) => (!isAe ? true : t.key === 'AUTO'))
                    .map((t) => ({
                      key: t.key,
                      label: isAe && t.key === 'AUTO' ? 'Auto-detect (CD/SA_MA)' : t.label,
                    }))}
                />
              </View>
            ) : null}

            <View style={{ marginTop: space(5) }}>
              <Button
                title={
                  busy
                    ? `Uploading ${done}/${uploadableFiles.length}...`
                    : allBlocked
                    ? 'Cannot upload: identical or restricted file(s)'
                    : uploadableFiles.length < picked.length
                    ? `Upload ${uploadableFiles.length} file${uploadableFiles.length === 1 ? '' : 's'} to ${siteId} (${picked.length - uploadableFiles.length} skipped)`
                    : picked.length
                    ? `Upload ${picked.length} file${picked.length === 1 ? '' : 's'} to ${siteId}`
                    : `Upload to ${siteId}`
                }
                disabled={!uploadableFiles.length || busy}
                onPress={upload}
              />
            </View>
            {error ? <ErrorView error={error} /> : null}

            {results.length > 0 ? (
              <View style={{ marginTop: space(5) }}>
                <Row style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: space(2) }}>
                  <Text style={{ fontWeight: '800', color: colors.text }}>
                    {okCount} of {results.length} uploaded
                  </Text>
                  {results.some((r) => r.isDuplicate) ? (
                    <Badge text={`${results.filter((r) => r.isDuplicate).length} duplicate${results.filter((r) => r.isDuplicate).length === 1 ? '' : 's'} blocked`} color={colors.danger} />
                  ) : null}
                </Row>
                {results.map((r) => {
                  const isWarn = r.ok && r.isDuplicate;
                  const isBlocked = !r.ok && r.isDuplicate;
                  const bg = isBlocked ? '#FEF2F2' : !r.ok ? '#FEF2F2' : isWarn ? '#FFFBEB' : '#F0FBF4';
                  const border = isBlocked ? '#FECACA' : !r.ok ? '#FAD0D0' : isWarn ? '#FDE68A' : '#C6EBD3';
                  const iconName = isBlocked ? 'x-circle' : !r.ok ? 'x-circle' : isWarn ? 'alert-triangle' : 'check-circle';
                  const iconColor = isBlocked ? colors.danger : !r.ok ? colors.danger : isWarn ? colors.warn : colors.ok;
                  const msgColor = isBlocked ? '#B91C1C' : !r.ok ? colors.danger : isWarn ? '#92400E' : '#3C6B4E';
                  return (
                    <View
                      key={r.name}
                      style={{
                        flexDirection: 'row',
                        gap: space(3),
                        padding: space(3.5),
                        marginBottom: space(2),
                        borderRadius: 12,
                        backgroundColor: bg,
                        borderWidth: 1,
                        borderColor: border,
                      }}
                    >
                      <Icon name={iconName} size={20} color={iconColor} />
                      <View style={{ flex: 1 }}>
                        <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                          <Text style={{ fontWeight: '700', color: colors.text }}>{r.name}</Text>
                          {isBlocked ? (
                            <Badge text="NOT UPLOADED · DUPLICATE" color={colors.danger} />
                          ) : isWarn ? (
                            <Badge text="DUPLICATE WARNING" color={colors.warn} />
                          ) : null}
                        </Row>
                        <Text style={{ fontSize: 12.5, color: msgColor, marginTop: 2, lineHeight: 17 }}>{r.message}</Text>
                        {r.hash ? (
                          <Text style={{ fontSize: 11, fontFamily: 'monospace', color: colors.muted, marginTop: 3 }}>
                            SHA-256: {r.hash.slice(0, 16)}...
                          </Text>
                        ) : null}
                      </View>
                    </View>
                  );
                })}
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
