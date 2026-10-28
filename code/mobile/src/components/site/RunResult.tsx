// The Result of a pipeline run: whether stage 4 saved a redlined drawing, and where it shows up.
import { router } from 'expo-router';
import React from 'react';
import { Linking, View } from 'react-native';
import { authedUrl } from '../../lib/api';
import { PipelineRun } from '../../lib/types';
import { colors, space } from '../theme';
import { Badge, Button, Card, IconBadge, Muted, Row, Section, Title } from '../ui';

export function RunResult({ run, siteId }: { run: PipelineRun; siteId: string }) {
  const s = run.SUMMARY ?? {};
  const d = s.redline_decision;
  if (!d) return null;
  const pdf: string | undefined = s.files?.redlined_cd_pdf;
  const saved = d.required && !!pdf;
  const name = pdf ? decodeURIComponent(pdf.split('/').pop() ?? pdf) : '';
  return (
    <Section title="Result">
      <Card style={{ borderColor: saved ? colors.danger : colors.ok, borderWidth: 1.5 }}>
        <Row style={{ alignItems: 'center', gap: space(3) }}>
          <IconBadge name={saved ? 'file-text' : 'check-circle'} color={saved ? colors.danger : colors.ok} size={40} />
          <View style={{ flex: 1 }}>
            <Title style={{ fontSize: 16 }}>{saved ? 'Redlined drawing saved' : 'No redlined drawing needed'}</Title>
            <Muted>{saved ? `${name} - the redline markup is on the CD drawing and is shown in the Redlines tab.` : d.reason}</Muted>
          </View>
        </Row>
        <Row style={{ gap: space(1), flexWrap: 'wrap', marginVertical: space(2) }}>
          <Badge text={`${d.redlines} redline${d.redlines === 1 ? '' : 's'}`} color={d.redlines ? colors.danger : colors.muted} />
          <Badge text={`${d.rfis} RFI${d.rfis === 1 ? '' : 's'}`} color={d.rfis ? colors.warn : colors.muted} />
        </Row>
        {saved ? (
          <Row style={{ gap: space(2), flexWrap: 'wrap' }}>
            <Button small title="View in Redlines tab" onPress={() => router.push({ pathname: '/site/[id]', params: { id: siteId, tab: 'redlines' } })} />
            <Button small kind="secondary" title="Open drawing" onPress={() => Linking.openURL(authedUrl(`/files/${pdf}`))} />
          </Row>
        ) : null}
      </Card>
    </Section>
  );
}
