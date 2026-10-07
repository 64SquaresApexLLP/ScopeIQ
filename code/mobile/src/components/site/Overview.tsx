import React from 'react';
import { View } from 'react-native';
import { SiteDetail } from '../../lib/types';
import { label, num, when } from '../../lib/format';
import { colors, space } from '../theme';
import { Badge, Card, KV, Muted, Row, Section, Title } from '../ui';
import { WorkflowActions } from '../WorkflowActions';

export function Overview({ d, reload }: { d: SiteDetail; reload: () => void }) {
  const st = d.site;
  const run = d.last_run[0];
  const req = d.requirements[0];
  return (
    <View>
      <Card>
        <Row style={{ justifyContent: 'space-between' }}><Title>{st.SITE_NAME}</Title><Badge text={st.WORKFLOW_STATE} color={colors.primary} /></Row>
        <Muted>{`${st.ADDRESS ?? ''}, ${st.CITY ?? ''} ${st.STATE ?? ''}`}</Muted>
        <View style={{ marginTop: space(2) }}>
          <KV k="Stream" v={`${st.STREAM} (${st.SERVICE_LINE ?? '-'})`} />
          <KV k="Structure" v={`${st.STRUCTURE_TYPE ?? '-'} ${st.HEIGHT_FT ? `${st.HEIGHT_FT} ft` : ''} - ${st.STRUCTURE_OWNER ?? ''}`} />
          <KV k="Project" v={`${st.PROJECT_NAME ?? '-'} (${st.PROJECT_TYPE ?? '-'})`} />
          <KV k="CX service provider" v={st.CX_SP} />
          <KV k="Scoping forecast" v={st.SCOPING_FORECAST} />
          <KV k="Current BOM" v={st.CURRENT_BOM_REV} />
          <KV k="Last pipeline run" v={run ? `${when(run.STARTED_AT)} - ${run.STATUS}` : 'never'} />
        </View>
      </Card>
      <Section title="Workflow">
        <Card><WorkflowActions actions={d.actions} endpoint={`/workflow/SITE_SCOPING/${st.SITE_ID}/transition`} entity="SITE" onDone={reload} /></Card>
      </Section>
      {d.ehs_alerts.length ? (
        <Section title="EH&S alerts">
          {d.ehs_alerts.map((a) => (
            <Card key={a.ALERT_ID} style={{ borderColor: colors.warn }}>
              <Row><Badge text={a.SEVERITY} /><Badge text={a.STATUS} /><Muted>{a.RULE_ID}</Muted></Row>
              <Muted style={{ color: colors.text, marginTop: 4 }}>{a.ALERT_TEXT}</Muted>
              <View style={{ marginTop: space(2) }}><WorkflowActions actions={a.ACTIONS ?? []} endpoint={`/ehs-alerts/${a.ALERT_ID}/transition`} entity="EHS_ALERT" onDone={reload} /></View>
            </Card>
          ))}
        </Section>
      ) : null}
      <Section title="Site requirements">
        <Card>
          {req ? (<>
            <KV k="Access" v={label(req.ACCESS_METHOD)} />
            <KV k="Crane / manlift days" v={`${num(req.CRANE_DAYS)} / ${num(req.MANLIFT_DAYS)}`} />
            <KV k="Rigging class" v={req.RIGGING_CLASS} />
            <KV k="Hold" v={req.HOLD ? 'YES - structure or RFI blocks construction' : 'No'} />
          </>) : <Muted>Not computed yet</Muted>}
        </Card>
      </Section>
      <Section title="Sectors (azimuth RFDS / CD / field)">
        {d.sectors.map((x) => (
          <Card key={x.SECTOR}>
            <Row style={{ justifyContent: 'space-between' }}><Title>{`Sector ${x.SECTOR}`}</Title>
              {x.AZ_RFDS != null && x.AZ_FIELD != null && Math.abs(((x.AZ_RFDS - x.AZ_FIELD + 540) % 360) - 180) > 5 ? <Badge text="azimuth off" color={colors.danger} /> : null}</Row>
            <Muted>{`${num(x.AZ_RFDS, 0)}° / ${num(x.AZ_CD, 0)}° / ${num(x.AZ_FIELD, 0)}°   sled CD ${x.SLED_CD ?? '-'} field ${x.SLED_FIELD ?? '-'}${x.NEW_FRAME ? '   new frame' : ''}`}</Muted>
          </Card>
        ))}
      </Section>
      <Section title="Trunk (cable) measurements">
        {d.trunks.map((t, i) => (
          <Card key={i}><Row style={{ justifyContent: 'space-between' }}><Title>{t.SOURCE}</Title><Muted>{`${num(t.TRUNK_COUNT, 0)} trunk(s)`}</Muted></Row>
            <Muted>{`vertical ${num(t.VERTICAL_FT)} ft, horizontal ${num(t.HORIZONTAL_FT)} ft, required ${num(t.REQUIRED_FT)} ft, specified ${num(t.SPECIFIED_FT)} ft`}</Muted></Card>
        ))}
      </Section>
      <Section title="Structural / mount analysis">
        {d.analyses.map((a) => (
          <Card key={a.KIND}><Row style={{ justifyContent: 'space-between' }}><Title>{`${a.KIND} ${a.REPORT_ID ?? ''}`}</Title><Badge text={a.RESULT} color={a.RESULT === 'PASS' ? colors.ok : a.RESULT === 'FAIL' ? colors.danger : colors.warn} /></Row>
            <Muted>{`capacity ${num(a.CAPACITY_PCT)}% -> ${num(a.CAPACITY_AFTER_PCT)}%, RFDS ${a.RFDS_REVISION ?? '-'}`}</Muted></Card>
        ))}
      </Section>
      <Section title="Milestones">
        <Card>{d.milestones.map((m) => <KV key={m.MILESTONE_SF_ID} k={m.NAME} v={`${m.STATUS ?? ''}  ${m.ACTUAL ?? m.FORECAST ?? ''}`} />)}</Card>
      </Section>
      <Section title="Workflow history">
        <Card>{d.workflow_history.length ? d.workflow_history.map((h) => <KV key={h.EVENT_ID} k={when(h.EVENT_TS)} v={`${h.FROM_STATE} -> ${h.TO_STATE} (${h.ACTION}) by ${h.ACTOR_USER_ID}`} />) : <Muted>No transitions yet</Muted>}</Card>
      </Section>
    </View>
  );
}
