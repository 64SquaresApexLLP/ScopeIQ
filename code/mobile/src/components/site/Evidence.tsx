import React, { useState } from 'react';
import { Image, Pressable, View } from 'react-native';
import { api } from '../../lib/api';
import { num } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { useApi } from '../../lib/useApi';
import { colors, space } from '../theme';
import { Badge, Card, Chips, Empty, ErrorView, Loading, Muted, Row, Section, Title } from '../ui';

export function Evidence({ siteId }: { siteId: string }) {
  const [sel, setSel] = useState<'selected' | 'all'>('selected');
  const d = useApi<{ frames: R[]; field_objects: R[] }>(`/sites/${siteId}/evidence?selected_only=${sel === 'selected'}`);
  const [big, setBig] = useState<string | null>(null);
  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading />;
  return (
    <View>
      <Chips value={sel} onChange={setSel} options={[{ key: 'selected', label: 'Best frame per sector' }, { key: 'all', label: 'All sampled frames' }]} />
      {!d.data.frames.length ? <Empty text="No drone video frames for this site." /> : null}
      {big ? (
        <Pressable onPress={() => setBig(null)}><Image source={{ uri: big }} style={{ width: '100%', aspectRatio: 16 / 9, borderRadius: 8, marginBottom: space(2) }} resizeMode="contain" /></Pressable>
      ) : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(2) }}>
        {d.data.frames.map((f) => (
          <Pressable key={f.FRAME_ID} onPress={() => setBig(api.fileUrl(f.URL))} style={{ width: '48%' }}>
            <Image source={{ uri: api.fileUrl(f.URL) }} style={{ width: '100%', aspectRatio: 16 / 9, borderRadius: 6, backgroundColor: colors.border }} />
            <Muted>{`${f.SECTOR ? `Sector ${f.SECTOR} - ` : ''}bearing ${num(f.BEARING_DEG, 0)}° - t=${num(f.TIME_S)}s`}</Muted>
          </Pressable>
        ))}
      </View>
      <Section title={`Field objects from drone data (${d.data.field_objects.length})`}>
        {d.data.field_objects.slice(0, 80).map((o, i) => (
          <Card key={o.OBJECT_ID ?? i}>
            <Row style={{ justifyContent: 'space-between' }}>
              <Title>{`${o.SECTOR ?? '-'}${o.POSITION ? `/${o.POSITION}` : ''} ${o.OBJECT_TYPE ?? ''}`}</Title>
              <Badge text={o.MODEL_GUESS ?? 'unidentified'} color={colors.primary} />
            </Row>
            <Muted>{`confidence ${num(o.CONFIDENCE, 2)} - ${o.METHOD ?? ''}${o.CENTER_HEIGHT_FT ? ` - ${num(o.CENTER_HEIGHT_FT)} ft` : ''}${o.FACING_AZ_DEG != null ? ` - faces ${num(o.FACING_AZ_DEG, 0)}°` : ''}`}</Muted>
          </Card>
        ))}
      </Section>
    </View>
  );
}
