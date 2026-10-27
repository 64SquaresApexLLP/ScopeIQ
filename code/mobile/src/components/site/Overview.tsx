import React from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { authedUrl } from '../../lib/api';
import { when } from '../../lib/format';
import { SiteDetail } from '../../lib/types';
import { colors, space } from '../theme';
import { Badge, Card, Icon, IconBadge, IconName, KV, Muted, Row, Section, Title } from '../ui';

const kb = (n?: number) =>
  !n ? '' : n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;

const fileIcon = (name: string): IconName =>
  (/\.(jpe?g|png|tif)$/i.test(name)
    ? 'image'
    : /\.(mp4|mov|avi)$/i.test(name)
    ? 'video'
    : /\.(xlsx|csv)$/i.test(name)
    ? 'grid'
    : /\.(laz|las)$/i.test(name)
    ? 'box'
    : 'file-text') as IconName;

const docTypeLabel = (typ: string) => {
  switch (typ) {
    case 'CD':
      return 'Construction Drawing (CD)';
    case 'RFDS':
      return 'RF Data Sheet (RFDS)';
    case 'MA_SA':
      return 'Mount & Structural Analysis';
    case 'BOM_REV0':
      return 'REV 0 Preliminary BOM';
    case 'DRONE_POINTCLOUD':
      return 'Drone LiDAR Point Cloud';
    case 'DRONE_VENDOR':
      return 'Vendor Survey Measurements';
    case 'DRONE_META':
      return 'Drone Flight Metadata';
    case 'DRONE_IMAGE':
      return 'Survey Photo / Orthophoto';
    case 'DRONE_VIDEO':
      return '360° Orbit Video';
    default:
      return typ.replace(/_/g, ' ');
  }
};

export function Overview({ d }: { d: SiteDetail; reload: () => void }) {
  const st = d.site;
  const run = d.last_run?.[0];
  const docs = d.documents ?? [];
  const check = d.revision_check;

  const currentDocs = docs.filter((x) => x.STATUS === 'CURRENT');
  const supersededDocs = docs.filter((x) => x.STATUS === 'SUPERSEDED');

  return (
    <View style={{ gap: space(4) }}>
      {/* 1. Site Overview Details */}
      <Card>
        <Row style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <View style={{ flex: 1 }}>
            <Title style={{ fontSize: 18, fontWeight: '800' }}>{st.SITE_NAME || st.SITE_ID}</Title>
            <Muted style={{ marginTop: 2 }}>
              {[st.ADDRESS, [st.CITY, st.STATE].filter(Boolean).join(', '), st.MARKET].filter(Boolean).join(' · ')}
            </Muted>
          </View>
          <Badge text={st.WORKFLOW_STATE || 'ASSIGNED'} color={colors.primary} />
        </Row>
        <View style={{ marginTop: space(3), borderTopWidth: 1, borderTopColor: colors.border, paddingTop: space(2) }}>
          <KV k="Site ID" v={st.SITE_ID} />
          <KV k="Stream" v={`${st.STREAM || '-'} (${st.SERVICE_LINE ?? '-'})`} />
          <KV
            k="Structure"
            v={`${st.STRUCTURE_TYPE ?? '-'} ${st.HEIGHT_FT ? `${st.HEIGHT_FT} ft` : ''} ${st.STRUCTURE_OWNER ? `· ${st.STRUCTURE_OWNER}` : ''}`}
          />
          <KV k="Project" v={`${st.PROJECT_NAME ?? '-'} (${st.PROJECT_TYPE ?? '-'})`} />
          <KV k="Coordinates" v={st.LATITUDE && st.LONGITUDE ? `${st.LATITUDE}, ${st.LONGITUDE}` : null} />
          <KV k="CX Service Provider" v={st.CX_SP ?? '-'} />
          <KV k="Current BOM Revision" v={st.CURRENT_BOM_REV ?? '-'} />
          <KV k="Last Pipeline Run" v={run ? `${when(run.STARTED_AT)} · ${run.STATUS}` : 'Never run'} />
        </View>
      </Card>

      {/* 2. Document Revision Checker Banner */}
      <Card style={{ backgroundColor: '#F8FAFF', borderColor: '#CBD5E8', padding: space(4) }}>
        <Row style={{ alignItems: 'center', gap: space(3), marginBottom: space(2.5) }}>
          <IconBadge name="shield" color={colors.ok} size={42} />
          <View style={{ flex: 1 }}>
            <Row style={{ alignItems: 'center', gap: space(2) }}>
              <Text style={{ fontWeight: '800', fontSize: 16, color: colors.text }}>Document Revision Checker</Text>
              <Badge text="VERIFIED" color={colors.ok} />
            </Row>
            <Text style={{ color: colors.muted, fontSize: 12.5, marginTop: 2 }}>
              {check?.message ||
                `${supersededDocs.length ? `${supersededDocs.length} older revision(s) superseded. ` : ''}Pipeline automatically verifies and selects the highest revision for all document types.`}
            </Text>
          </View>
        </Row>

        {/* Dynamic rule confirmation notice */}
        <View style={{ backgroundColor: '#fff', borderRadius: 12, padding: space(3), borderWidth: 1, borderColor: '#E2E8F0', marginTop: space(1) }}>
          <Row style={{ alignItems: 'center', gap: space(2) }}>
            <Icon name="check-circle" size={16} color={colors.ok} />
            <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }}>Revision Selection Rule Enforced:</Text>
          </Row>
          <Text style={{ fontSize: 12, color: colors.muted, marginTop: 4, lineHeight: 18 }}>
            When multiple revisions exist for a document (e.g. CD Drawing revision 0 and 1), the pipeline automatically picks{' '}
            <Text style={{ fontWeight: '700', color: colors.ok }}>REV 1</Text> and marks older revisions as{' '}
            <Text style={{ fontWeight: '700', color: colors.warn }}>SUPERSEDED</Text>. Scoping analysis and BOM calculations always run against the latest verified revision.
          </Text>
        </View>

        {/* Metric counts */}
        <Row style={{ marginTop: space(3), gap: space(3), flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 100, backgroundColor: '#fff', padding: space(2.5), borderRadius: 10, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.muted, textTransform: 'uppercase' }}>Total Docs</Text>
            <Text style={{ fontSize: 18, fontWeight: '800', color: colors.text, marginTop: 2 }}>{docs.length}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 100, backgroundColor: '#F0FBF4', padding: space(2.5), borderRadius: 10, borderWidth: 1, borderColor: '#C6EBD3' }}>
            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.ok, textTransform: 'uppercase' }}>Latest (Picked)</Text>
            <Text style={{ fontSize: 18, fontWeight: '800', color: colors.ok, marginTop: 2 }}>{currentDocs.length}</Text>
          </View>
          {supersededDocs.length > 0 ? (
            <View style={{ flex: 1, minWidth: 100, backgroundColor: '#FFFBEB', padding: space(2.5), borderRadius: 10, borderWidth: 1, borderColor: '#FDE68A' }}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: colors.warn, textTransform: 'uppercase' }}>Superseded (Older)</Text>
              <Text style={{ fontSize: 18, fontWeight: '800', color: colors.warn, marginTop: 2 }}>{supersededDocs.length}</Text>
            </View>
          ) : null}
        </Row>
      </Card>

      {/* 3. Documents with their Current Revision */}
      <Section title={`Documents & Current Revisions (${docs.length})`}>
        {docs.length === 0 ? (
          <Card>
            <Muted style={{ textAlign: 'center', padding: space(4) }}>
              No documents registered for this site yet. Click 'Run Pipeline' above to ingest site documents.
            </Muted>
          </Card>
        ) : (
          docs.map((x) => {
            const isCurrent = x.STATUS === 'CURRENT';
            const isSuperseded = x.STATUS === 'SUPERSEDED';
            const rev = x.REVISION || (x.REVISION_RANK != null && x.REVISION_RANK > 0 ? `REV ${x.REVISION_RANK}` : 'REV 0');

            return (
              <Card
                key={x.DOC_ID || x.FILE_NAME}
                onPress={() => (x.DOC_ID ? Linking.openURL(authedUrl(`/documents/${x.DOC_ID}/download`)) : undefined)}
                style={{
                  marginBottom: space(2),
                  borderLeftWidth: 4,
                  borderLeftColor: isCurrent ? colors.ok : isSuperseded ? colors.warn : colors.muted,
                  backgroundColor: isSuperseded ? '#FCFCFD' : '#fff',
                }}
              >
                <Row style={{ alignItems: 'flex-start', gap: space(3) }}>
                  <IconBadge name={fileIcon(x.FILE_NAME)} color={isCurrent ? colors.accent : colors.muted} size={36} />
                  <View style={{ flex: 1 }}>
                    <Row style={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
                      <Text style={{ fontWeight: '800', fontSize: 14, color: colors.text }}>
                        {docTypeLabel(x.DOC_TYPE)}
                      </Text>
                      <Row style={{ alignItems: 'center', gap: space(1.5) }}>
                        {x.REVISION ? (
                          <View style={{ backgroundColor: colors.soft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, borderWidth: 1, borderColor: '#C9D3F5' }}>
                            <Text style={{ fontSize: 11, fontWeight: '800', color: colors.accent }}>{x.REVISION}</Text>
                          </View>
                        ) : null}
                        <Badge
                          text={isCurrent ? '✓ Picked (Latest)' : isSuperseded ? '⚠ Superseded (Older)' : x.STATUS}
                          color={isCurrent ? colors.ok : isSuperseded ? colors.warn : colors.muted}
                        />
                      </Row>
                    </Row>
                    <Text style={{ fontSize: 13, color: isSuperseded ? colors.muted : colors.text, fontWeight: '600', marginTop: 4 }} numberOfLines={1}>
                      {x.FILE_NAME}
                    </Text>
                    <Row style={{ marginTop: 4, alignItems: 'center', gap: space(2) }}>
                      <Muted style={{ fontSize: 12 }}>
                        {[x.FILE_FORMAT, kb(x.SIZE_BYTES), x.DOC_DATE].filter(Boolean).join(' · ')}
                      </Muted>
                      {isSuperseded ? (
                        <Text style={{ fontSize: 11, color: colors.warn, fontWeight: '700' }}>
                          (Superseded by newer revision)
                        </Text>
                      ) : null}
                    </Row>
                  </View>
                </Row>
              </Card>
            );
          })
        )}
      </Section>
    </View>
  );
}
