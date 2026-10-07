// Workflow action bar used by every entity (site, discrepancy, redline, RFI, BOM revision, EH&S alert).
// Actions come from the server for the signed-in role; reason codes and comments are asked for when the
// transition requires them, and every transition is audited server-side.
import React, { useEffect, useState } from 'react';
import { Modal, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { api, ApiError } from '../lib/api';
import { getLogger } from '../lib/logger';
import { ReasonCode, WorkflowAction } from '../lib/types';
import { colors, space } from './theme';
import { Button, ErrorView, Muted, Row, s, Title } from './ui';

const log = getLogger('workflow');
let reasonCache: ReasonCode[] | null = null;

export function useReasonCodes(appliesTo?: string) {
  const [codes, setCodes] = useState<ReasonCode[]>(reasonCache ?? []);
  useEffect(() => {
    if (reasonCache) return;
    api.get<ReasonCode[]>('/reference-codes/reasons').then((r) => {
      reasonCache = r;
      setCodes(r);
    }).catch((e) => log.warn('reason codes not loaded', { error: String(e) }));
  }, []);
  return appliesTo ? codes.filter((c) => !c.APPLIES_TO || c.APPLIES_TO.split(';').includes(appliesTo)) : codes;
}

export function ReasonPicker({ value, onChange, appliesTo }: { value: string | null; onChange: (c: string) => void; appliesTo?: string }) {
  const codes = useReasonCodes(appliesTo);
  return (
    <ScrollView style={{ maxHeight: 220 }}>
      {codes.map((c) => (
        <Pressable key={c.REASON_CODE} onPress={() => onChange(c.REASON_CODE)} accessibilityRole="radio" accessibilityState={{ checked: value === c.REASON_CODE }}
          style={{ padding: space(2), borderRadius: 6, backgroundColor: value === c.REASON_CODE ? colors.primary + '18' : undefined }}>
          <Text style={{ fontWeight: '700', color: colors.text }}>{c.REASON_CODE}</Text>
          <Muted>{`${c.DESCRIPTION} (${c.FAULT_PARTY})`}</Muted>
        </Pressable>
      ))}
    </ScrollView>
  );
}

interface Props {
  actions: (WorkflowAction | string)[];
  endpoint: string;                // POST target, receives {action, reason_code, comment}
  entity: string;                  // reason-code filter (DISCREPANCY, BOM_LINE ...)
  onDone: () => void;
  details?: WorkflowAction[];      // full action definitions when `actions` are names only
}

export function WorkflowActions({ actions, endpoint, entity, onDone, details }: Props) {
  const [pending, setPending] = useState<WorkflowAction | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const defs: WorkflowAction[] = actions.map((a) =>
    typeof a === 'string'
      ? details?.find((d) => d.action === a) ?? { action: a, to_state: '', requires_reason: false, requires_comment: false, description: '', roles: [] }
      : a,
  );

  const submit = async (a: WorkflowAction, rc: string | null, cm: string) => {
    setBusy(true);
    setError(null);
    try {
      await api.post(endpoint, { action: a.action, reason_code: rc, comment: cm || null });
      log.info(`${a.action} on ${endpoint}`);
      setPending(null);
      setReason(null);
      setComment('');
      onDone();
    } catch (e) {
      const err = e as ApiError;
      // the server is the authority on what a transition needs; ask for it and retry
      if (err.status === 400 && /reason|comment/i.test(err.message)) {
        setPending({ ...a, requires_reason: a.requires_reason || /reason/i.test(err.message), requires_comment: a.requires_comment || /comment/i.test(err.message) });
      }
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  if (!defs.length) return <Muted>No actions available for your role in this state.</Muted>;
  return (
    <View>
      <Row>
        {defs.map((a) => (
          <Button key={a.action} small kind={/DISMISS|REJECT|RETURN|REQUEST_CHANGES/.test(a.action) ? 'secondary' : 'primary'}
            title={a.action.replace(/_/g, ' ')} disabled={busy}
            onPress={() => (a.requires_reason || a.requires_comment ? setPending(a) : submit(a, null, ''))} />
        ))}
      </Row>
      {error && !pending ? <View style={{ marginTop: space(2) }}><ErrorView error={error} /></View> : null}
      <Modal visible={!!pending} transparent animationType="slide" onRequestClose={() => setPending(null)}>
        <View style={{ flex: 1, backgroundColor: '#0006', justifyContent: 'flex-end' }}>
          <View style={{ backgroundColor: colors.card, padding: space(4), borderTopLeftRadius: 16, borderTopRightRadius: 16, gap: space(2) }}>
            <Title>{pending?.action.replace(/_/g, ' ')}</Title>
            {pending?.description ? <Muted>{pending.description}</Muted> : null}
            {pending?.requires_reason ? (<><Muted>Reason code (required)</Muted><ReasonPicker value={reason} onChange={setReason} appliesTo={entity} /></>) : null}
            <TextInput style={[s.input, { minHeight: 70 }]} multiline placeholder={pending?.requires_comment ? 'Comment (required)' : 'Comment (optional)'}
              value={comment} onChangeText={setComment} />
            {error ? <ErrorView error={error} /> : null}
            <Row>
              <Button title="Cancel" kind="secondary" onPress={() => { setPending(null); setError(null); }} />
              <Button title={busy ? 'Saving...' : 'Confirm'} disabled={busy || (!!pending?.requires_reason && !reason) || (!!pending?.requires_comment && !comment.trim())}
                onPress={() => pending && submit(pending, reason, comment)} />
            </Row>
          </View>
        </View>
      </Modal>
    </View>
  );
}
