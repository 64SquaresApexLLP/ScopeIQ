// What a service provider is given for a site: from the handshake onward (once the BOM is generated, all redlines are resolved,
// and the package is sent for review), the final construction drawings, scope of work, and BOM, which it agrees to or asks to change.
import React, { useMemo, useState } from 'react';
import { Linking, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { authedUrl } from '../../lib/api';
import { label, SECTOR, when } from '../../lib/format';
import { ProviderView, WorkflowAction } from '../../lib/types';
import { mutateApi, useApi } from '../../lib/useApi';
import { FilePreviewModal, FilePreviewTarget } from '../FilePreviewModal';
import { colors, radius, space } from '../theme';
import { Badge, Button, Card, EmptyState, ErrorView, Icon, Loading, s } from '../ui';
import { WorkflowActions } from '../WorkflowActions';

const size = (n?: number | null) => (!n ? '' : n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

/** Shown in place of the scope of work or the BOM until it has been sent to the provider. */
function NotSent({ what, asked }: { what: string; asked: boolean }) {
  return (
    <Card>
      <EmptyState icon="clock" title={asked ? 'Your changes are being applied' : `The ${what} is not available yet`}
        text={asked ? `The updated ${what} appears here when it is ready for your review.` : `It appears here when it is ready for your review.`} />
    </Card>
  );
}

export function ProviderDrawings({ siteId }: { siteId: string }) {
  const { data, error, loading, reload } = useApi<ProviderView>(`/sites/${siteId}/provider`);
  const [target, setTarget] = useState<FilePreviewTarget | null>(null);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorView error={error} onRetry={reload} />;
  const drawings = data?.drawings ?? [];
  return (
    <Card padded={false}>
      <View style={{ padding: space(5), paddingBottom: space(3) }}>
        <Text style={{ fontSize: 15.5, fontWeight: '700', color: colors.text }}>Construction drawings</Text>
      </View>
      {drawings.length === 0 ? (
        <EmptyState
          icon="file-text"
          title="Drawings are not available yet"
          text={data?.requests.length
            ? 'Updated drawings appear here once your change request is processed and ready for your review.'
            : 'They appear here once the BOM is approved and sent for your review.'}
        />
      ) : (
        drawings.map((d) => (
          <View key={d.DOC_ID} style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: space(3), paddingHorizontal: space(5), paddingVertical: space(3), borderTopWidth: 1, borderTopColor: colors.border }}>
            <View style={{ width: 34, height: 34, borderRadius: 8, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center' }}>
              <Icon name="file-text" size={16} color={colors.accent} />
            </View>
            <View style={{ flex: 1, minWidth: 200 }}>
              <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }} numberOfLines={1}>{d.FILE_NAME}</Text>
              <Text style={{ fontSize: 12.5, color: colors.muted, marginTop: 1 }}>{[d.FILE_FORMAT, size(d.SIZE_BYTES)].filter(Boolean).join(' · ')}</Text>
            </View>
            {d.REVISION ? <Badge text={d.REVISION} color={colors.accent} /> : null}
            <Button small kind="secondary" icon="eye" title="View" onPress={() => setTarget({ name: d.FILE_NAME, docId: d.DOC_ID, siteId, size: d.SIZE_BYTES })} />
            <Button small kind="secondary" icon="download" title="Download" onPress={() => Linking.openURL(authedUrl(`/documents/${d.DOC_ID}/download?disposition=attachment`))} />
          </View>
        ))
      )}
      <FilePreviewModal target={target} onClose={() => setTarget(null)} />
    </Card>
  );
}

const actionColor = (a?: string) => (a === 'REMOVED' || a === 'Remove' ? colors.danger : a === 'EXISTING' ? colors.muted : a === 'RELOCATED' || a === 'REUSED' ? colors.info : colors.ok);

/** The scope of work: what is installed, removed or kept, by sector. */
export function ProviderScope({ siteId }: { siteId: string }) {
  const { data, error, loading, reload } = useApi<ProviderView>(`/sites/${siteId}/provider`);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorView error={error} onRetry={reload} />;
  if (!data?.scope.released) return <NotSent what="scope of work" asked={!!data?.requests.length} />;
  const sectors = [...new Set(data.scope.items.map((x) => x.SECTOR || 'SITE'))];
  return (
    <View style={{ gap: space(3) }}>
      {data.scope.items.length === 0 ? <Card><EmptyState icon="layers" title="No scope of work recorded" /></Card> : sectors.map((sec) => (
        <Card key={sec} padded={false}>
          <View style={{ padding: space(4), paddingBottom: space(2) }}>
            <Text style={{ fontSize: 14.5, fontWeight: '700', color: colors.text }}>Sector {SECTOR[sec] ? `${SECTOR[sec]} (${sec})` : sec}</Text>
          </View>
          {data.scope.items.filter((x) => (x.SECTOR || 'SITE') === sec).map((x, i) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), paddingHorizontal: space(4), paddingVertical: space(2.5), borderTopWidth: 1, borderTopColor: colors.border }}>
              <Text style={{ flex: 1, fontSize: 13.5, color: colors.text }}>
                {[x.POSITION ? `Position ${x.POSITION}` : null, x.KIND ? label(x.KIND) : null, x.CATALOG_KEY].filter(Boolean).join(' · ')}
                {x.FROM_POSITION ? <Text style={{ color: colors.muted }}>{`  (from position ${x.FROM_POSITION})`}</Text> : null}
              </Text>
              <Badge text={label(x.ACTION)} color={actionColor(x.ACTION)} />
            </View>
          ))}
        </Card>
      ))}
    </View>
  );
}

export function ProviderBom({ siteId }: { siteId: string }) {
  const { data, error, loading, reload } = useApi<ProviderView>(`/sites/${siteId}/provider`);
  const [q, setQ] = useState('');
  const [action, setAction] = useState<'ALL' | 'Install' | 'Remove'>('ALL');
  const lines = data?.bom.lines ?? [];
  const rows = useMemo(() => lines.filter((b) => (action === 'ALL' || b.ACTION === action)
    && (!q.trim() || [b.CATEGORY, b.MODEL, b.DESCRIPTION, b.SECTOR].some((v) => String(v ?? '').toLowerCase().includes(q.trim().toLowerCase())))), [lines, q, action]);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorView error={error} onRetry={reload} />;
  if (!data?.bom.released) return <NotSent what="BOM" asked={!!data?.requests.length} />;
  return (
    <Card padded={false}>
      <View style={{ padding: space(5), gap: space(3) }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
          <Text style={{ fontSize: 15.5, fontWeight: '700', color: colors.text }}>Bill of materials</Text>
          <Text style={{ fontSize: 13, color: colors.muted }}>{lines.length} lines</Text>
          {data.bom.approved ? <Badge text="Approved" color={colors.ok} dot /> : null}
        </View>
        <View style={{ flexDirection: 'row', gap: space(2), alignItems: 'center', flexWrap: 'wrap' }}>
          <TextInput style={[s.input, { flex: 1, minWidth: 200 }]} placeholder="Filter by model, category or sector" placeholderTextColor="#A9B3C2" value={q} onChangeText={setQ} />
          {(['ALL', 'Install', 'Remove'] as const).map((m) => (
            <Pressable key={m} onPress={() => setAction(m)} style={{ paddingHorizontal: space(2.5), paddingVertical: space(1.5), borderRadius: radius.md, borderWidth: 1,
              borderColor: action === m ? '#BFD3FB' : colors.border, backgroundColor: action === m ? colors.soft : '#fff' }}>
              <Text style={{ fontSize: 12.5, fontWeight: '600', color: action === m ? colors.accent : colors.text }}>{m === 'ALL' ? 'All' : m}</Text>
            </Pressable>
          ))}
        </View>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ minWidth: '100%' }}>
        <View style={{ minWidth: 760, flex: 1 }}>
          <View style={{ flexDirection: 'row', paddingVertical: space(2), paddingHorizontal: space(5), backgroundColor: colors.surfaceAlt, borderTopWidth: 1, borderBottomWidth: 1, borderColor: colors.border }}>
            {[['Category', 130], ['Model', 0], ['Sector', 70], ['Qty', 60], ['Action', 90], ['Supplied by', 100]].map(([t, w]) => (
              <Text key={t as string} style={[{ fontSize: 11, fontWeight: '600', color: colors.muted, letterSpacing: 0.4, textTransform: 'uppercase' }, w ? { width: w as number } : { flex: 1 }]}>{t}</Text>
            ))}
          </View>
          {rows.map((b, i) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: space(2), paddingHorizontal: space(5), borderBottomWidth: 1, borderBottomColor: colors.border }}>
              <Text style={{ width: 130, fontSize: 13, color: colors.text }} numberOfLines={1}>{b.CATEGORY}</Text>
              <View style={{ flex: 1, paddingRight: space(2) }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }} numberOfLines={1}>{b.MODEL || b.DESCRIPTION}</Text>
                {b.MODEL && b.DESCRIPTION ? <Text style={{ fontSize: 11.5, color: colors.muted }} numberOfLines={1}>{b.DESCRIPTION}</Text> : null}
              </View>
              <Text style={{ width: 70, fontSize: 13, color: colors.muted }}>{b.SECTOR || ''}</Text>
              <Text style={{ width: 60, fontSize: 13, fontWeight: '600', color: colors.text }}>{b.TOTAL_QTY ?? ''}{b.UOM && b.UOM !== 'EA' ? ` ${b.UOM}` : ''}</Text>
              <View style={{ width: 90, flexDirection: 'row' }}><Badge text={b.ACTION} color={b.ACTION === 'Remove' ? colors.danger : colors.ok} /></View>
              <Text style={{ width: 100, fontSize: 12.5, color: colors.muted }}>{b.SUPPLY || ''}</Text>
            </View>
          ))}
          {rows.length === 0 ? <EmptyState icon="filter" title="No lines match" text="Change the filter to see more." /> : null}
        </View>
      </ScrollView>
    </Card>
  );
}

/** The provider's answer in the handshake (agree, or request changes), a request after final approval, and the requests already made.
 *  What is on offer comes from the workflow, so it appears only when the provider can act. */
export function ProviderReview({ siteId }: { siteId: string }) {
  const offered = useApi<{ state: string; actions: WorkflowAction[] }>(`/workflow/SITE_SCOPING/${siteId}/actions`);
  const view = useApi<ProviderView>(`/sites/${siteId}/provider`);
  const actions = offered.data?.actions ?? [];
  const requests = view.data?.requests ?? [];
  if (!actions.length && !requests.length) return null;
  const reviewing = view.data?.phase === 'REVIEW';
  return (
    <Card padded={false}>
      <View style={{ padding: space(5), gap: space(2) }}>
        <Text style={{ fontSize: 15.5, fontWeight: '700', color: colors.text }}>{reviewing ? 'Your review' : 'Change requests'}</Text>
        {actions.length ? (
          <>
            <Text style={{ fontSize: 13, color: colors.muted }}>
              {reviewing ? 'Agree to the scope of work and BOM, or ask for changes.' : 'Something to change in the drawings or the BOM? Tell us what and why.'}
            </Text>
            <View style={{ marginTop: space(1) }}>
              <WorkflowActions actions={actions} endpoint={`/workflow/SITE_SCOPING/${siteId}/transition`} entity="SITE_SCOPING"
                onDone={() => { mutateApi(`/workflow/SITE_SCOPING/${siteId}`); mutateApi(`/sites/${siteId}`); mutateApi('/sites'); void offered.reload(true); void view.reload(true); }} />
            </View>
          </>
        ) : null}
      </View>
      {requests.map((r, i) => (
        <View key={i} style={{ paddingHorizontal: space(5), paddingVertical: space(3), borderTopWidth: 1, borderTopColor: colors.border, gap: 2 }}>
          <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{r.reason || 'Change requested'}</Text>
          {r.comment ? <Text style={{ fontSize: 13, color: colors.text }}>"{r.comment}"</Text> : null}
          <Text style={{ fontSize: 11.5, color: colors.muted }}>{when(r.when)}</Text>
        </View>
      ))}
    </Card>
  );
}
