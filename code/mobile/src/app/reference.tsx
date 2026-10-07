import React, { useState } from 'react';
import { ScrollView } from 'react-native';
import { Button, Card, Chips, ErrorView, KV, Loading, Muted, s } from '../components/ui';
import { api, ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { Row as R } from '../lib/types';
import { useApi } from '../lib/useApi';

export default function Reference() {
  const tables = useApi<{ table: string; rows: number; version: string }[]>('/reference');
  const [t, setT] = useState('material_catalog');
  const rows = useApi<R[]>(`/reference/${t}`);
  const { can } = useAuth();
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const reload = async () => {
    try {
      const c = await api.post<Record<string, number>>('/reference/reload');
      setMsg(`Reloaded ${Object.keys(c).length} tables from the CSV library`);
      void tables.reload();
    } catch (e) {
      setErr(e as ApiError);
    }
  };
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content}>
      <Muted>Business rules are data: edit the CSV library (reference_data/), then reload. Rows carry version and effective dates.</Muted>
      {can('ADMIN') ? <Button small kind="secondary" title="Reload from CSV" onPress={reload} /> : null}
      {msg ? <Muted>{msg}</Muted> : null}
      {err ? <ErrorView error={err} /> : null}
      <Chips value={t} onChange={setT} options={(tables.data ?? []).map((x) => ({ key: x.table, label: `${x.table} (${x.rows})` }))} />
      {rows.error ? <ErrorView error={rows.error} /> : !rows.data ? <Loading /> : rows.data.slice(0, 200).map((r, i) => (
        <Card key={i}>{Object.entries(r).filter(([, v]) => v !== '' && v != null).map(([k, v]) => <KV key={k} k={k} v={String(v)} />)}</Card>
      ))}
    </ScrollView>
  );
}
