import React from 'react';
import { View } from 'react-native';
import { SECTOR } from '../../lib/format';
import { Row as R } from '../../lib/types';
import { colors } from '../theme';
import { Badge, Card, Empty, Muted, Row, Title } from '../ui';

export function Delta({ rows }: { rows: R[] }) {
  if (!rows.length) return <Empty text="No equipment delta yet - run the pipeline." />;
  const sectors = [...new Set(rows.map((r) => r.SECTOR))];
  return (
    <View>
      <Muted>Final configuration (RFDS for RF, field for physical conditions, MA for mounts) against what is on site.</Muted>
      {sectors.map((sec) => (
        <Card key={sec}>
          <Title>{SECTOR[sec] ? `${SECTOR[sec]} (${sec})` : sec}</Title>
          {rows.filter((r) => r.SECTOR === sec).map((r) => (
            <Row key={r.SEQ} style={{ marginTop: 6, justifyContent: 'space-between' }}>
              <View style={{ flex: 1 }}>
                <Muted style={{ color: colors.text }}>{`${r.POSITION ? `Pos ${r.POSITION} ` : ''}${r.KIND}: ${r.CATALOG_KEY}${r.RAD_CENTER_FT ? ` @ ${r.RAD_CENTER_FT} ft` : ''}`}</Muted>
                <Muted numberOfLines={1}>{`${r.BASIS ?? ''}${r.SOURCE_REF ? ` - ${r.SOURCE_REF}` : ''}`}</Muted>
              </View>
              <Badge text={r.ACTION} />
            </Row>
          ))}
        </Card>
      ))}
    </View>
  );
}
