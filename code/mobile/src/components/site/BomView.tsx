// Bill of materials workspace: summary, rules that were not applied, the BOM lines with the rule and calculation behind
// each one, the generated workbook as it will be exported, and the issues the engine raised.
import React, { useMemo, useState } from 'react';
import { Linking, ScrollView, Text, View } from 'react-native';
import { authedUrl } from '../../lib/api';
import { num, show } from '../../lib/format';
import { useApi } from '../../lib/useApi';
import { colors, font, radius, space, tint } from '../theme';
import { Badge, Banner, Button, Card, Chips, Column, DataTable, EmptyState, ErrorView, Icon, Loading, s, SearchBox, Stat, Tabs } from '../ui';

interface BomSheet { name: string; columns: string[]; rows: (string | number | boolean | null)[][] }
interface BomPreviewResponse {
  available: boolean; site_id: string; run_id: string | null; file_name: string | null; download_path: string | null;
  summary: { lines?: number; install_lines?: number; remove_lines?: number; install_qty?: number; remove_qty?: number; needs_review?: number; issues_count?: number; total_material_cost?: number; revision?: string | null };
  sheets: BomSheet[]; lines: Record<string, any>[]; issues: Record<string, any>[];
}

type View_ = 'lines' | 'workbook' | 'issues';
type ActionFilter = 'ALL' | 'Install' | 'Remove' | 'REVIEW';
const NOT_APPLIED = new Set(['RULE_NOT_APPLIED', 'RULE_CHILD_UNKNOWN']);
const money = (v: number) => `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const needsReview = (l: Record<string, any>) => /review|not in/i.test(String(l.STATUS ?? ''));

// ------------------------------------------------------------------ workbook preview (what the export contains)
const COL_WIDTHS: Record<string, number> = {
  'Site ID': 84, Market: 68, Sector: 76, Technology: 86, Band: 84, 'Equipment Category': 148, Manufacturer: 112, Model: 164, 'Manufacturer P/N': 140,
  'Customer P/N': 110, Description: 290, UOM: 56, 'Design Qty': 84, 'Spare Qty': 80, 'Total Qty': 80, 'Unit Cost ($)': 108, 'Total Cost ($)': 114,
  'Supply (CFM/VFM)': 120, Action: 88, Source: 160, Drawing: 115, 'BOM Rule': 86, Revision: 150, Status: 185, Severity: 85, Code: 160, Rule: 85, Message: 480,
};
const NUMERIC_COLS = new Set(['Design Qty', 'Spare Qty', 'Total Qty']);
const CURRENCY_COLS = new Set(['Unit Cost ($)', 'Total Cost ($)']);
const colWidth = (n: string) => COL_WIDTHS[n] ?? 125;
const cellText = (v: string | number | boolean | null | undefined, c: string) =>
  v === null || v === undefined || v === '' ? '—' : typeof v === 'number' ? (CURRENCY_COLS.has(c) ? money(v) : NUMERIC_COLS.has(c) ? num(v) : String(v)) : String(v);

function WorkbookGrid({ sheet, query }: { sheet: BomSheet; query: string }) {
  const statusIdx = sheet.columns.findIndex((c) => c.toLowerCase() === 'status');
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? sheet.rows.filter((r) => r.some((c) => c != null && String(c).toLowerCase().includes(q))) : sheet.rows;
  }, [sheet.rows, query]);
  const total = 46 + sheet.columns.reduce((a, c) => a + colWidth(c), 0);
  return (
    <View style={[s.card, { padding: 0, overflow: 'hidden' }]}>
      <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{ width: total }}>
          <View style={{ flexDirection: 'row', backgroundColor: colors.surfaceAlt, borderBottomWidth: 1, borderBottomColor: colors.border }}>
            <View style={{ width: 46, paddingVertical: 9, alignItems: 'center', borderRightWidth: 1, borderRightColor: colors.border }}><Text style={s.thText}>#</Text></View>
            {sheet.columns.map((c, i) => (
              <View key={`${c}-${i}`} style={{ width: colWidth(c), paddingVertical: 9, paddingHorizontal: 8, borderRightWidth: i < sheet.columns.length - 1 ? 1 : 0, borderRightColor: colors.border }}>
                <Text style={[s.thText, { textAlign: NUMERIC_COLS.has(c) || CURRENCY_COLS.has(c) ? 'right' : 'left' }]} numberOfLines={1}>{c}</Text>
              </View>
            ))}
          </View>
          {rows.length === 0 ? <View style={{ padding: space(5) }}><Text style={s.muted}>No rows match the search.</Text></View> : rows.map((row, ri) => {
            const review = statusIdx >= 0 && /review|not in/i.test(String(row[statusIdx] ?? ''));
            return (
              <View key={ri} style={{ flexDirection: 'row', backgroundColor: review ? tint.warn.bg : '#fff', borderBottomWidth: ri < rows.length - 1 ? 1 : 0, borderBottomColor: colors.border }}>
                <View style={{ width: 46, paddingVertical: 7, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surfaceAlt, borderRightWidth: 1, borderRightColor: colors.border }}>
                  <Text style={{ fontSize: 11, color: colors.muted }}>{ri + 1}</Text>
                </View>
                {sheet.columns.map((c, ci) => {
                  const raw = row[ci];
                  const right = NUMERIC_COLS.has(c) || CURRENCY_COLS.has(c);
                  return (
                    <View key={ci} style={{ width: colWidth(c), paddingVertical: 7, paddingHorizontal: 8, justifyContent: 'center', alignItems: right ? 'flex-end' : 'flex-start', borderRightWidth: ci < sheet.columns.length - 1 ? 1 : 0, borderRightColor: colors.border }}>
                      {c.toLowerCase() === 'action' && raw ? <Badge text={String(raw)} color={raw === 'Install' ? colors.ok : raw === 'Remove' ? colors.danger : colors.neutral} />
                        : <Text style={{ fontSize: 12, color: colors.text, fontWeight: c === 'Total Qty' ? '600' : '400', textAlign: right ? 'right' : 'left' }} numberOfLines={2}>{cellText(raw, c)}</Text>}
                    </View>
                  );
                })}
              </View>
            );
          })}
        </View>
      </ScrollView>
    </View>
  );
}

// ------------------------------------------------------------------ calculation detail behind a line
function calc(l: Record<string, any>): string {
  const t = l.TRACE && typeof l.TRACE === 'object' ? l.TRACE : null;
  const parts: string[] = [];
  if (l.DESIGN_QTY != null) parts.push(`${num(l.DESIGN_QTY)} design${l.SPARE_QTY ? ` + ${num(l.SPARE_QTY)} spare` : ''}`);
  if (t) {
    const entries = Object.entries(t).filter(([, v]) => v != null && v !== '' && typeof v !== 'object').slice(0, 4);
    if (entries.length) parts.push(entries.map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(', '));
  } else if (l.SOURCE) parts.push(`source: ${l.SOURCE}`);
  return parts.join('  ·  ');
}

export function BomView({ siteId }: { siteId: string }) {
  const d = useApi<BomPreviewResponse>(`/bom/sites/${siteId}/preview`);
  const [view, setView] = useState<View_>('lines');
  const [sheetIdx, setSheetIdx] = useState(0);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<ActionFilter>('ALL');

  const lines = d.data?.lines ?? [];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return lines.filter((l) => {
      if (filter === 'REVIEW' ? !needsReview(l) : filter !== 'ALL' && String(l.ACTION ?? '') !== filter) return false;
      return !q || [l.SECTOR, l.CATEGORY, l.MANUFACTURER, l.MODEL, l.MANUFACTURER_PN, l.CATALOG_KEY, l.DESCRIPTION, l.RULE_ID, l.STATUS].some((v) => v != null && String(v).toLowerCase().includes(q));
    });
  }, [lines, query, filter]);

  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading rows={5} />;
  if (!d.data.available) {
    return (
      <Card><EmptyState icon="list" title="No bill of materials yet"
        text="The BOM is generated in stage 6, which runs only when stages 1 to 4 succeed and no redlines or RFIs are open. Check the Pipeline tab for where the latest run stopped." /></Card>
    );
  }

  const { summary, sheets, download_path, file_name, issues } = d.data;
  const notApplied = issues.filter((i) => NOT_APPLIED.has(String(i.code ?? i.CODE ?? '')));
  const otherIssues = issues.filter((i) => !NOT_APPLIED.has(String(i.code ?? i.CODE ?? '')));
  const rulesUsed = new Set(lines.map((l) => l.RULE_ID).filter(Boolean));
  const review = lines.filter(needsReview).length;
  const sheet = sheets[sheetIdx] ?? sheets[0];

  const columns: Column<Record<string, any>>[] = [
    { key: 'mat', title: 'Material', flex: 2.2, render: (l) => (
      <View style={{ gap: 2 }}>
        <Text style={{ fontSize: 13.5, fontWeight: '600', color: colors.text }} numberOfLines={1}>{l.MODEL || l.CATALOG_KEY || '—'}</Text>
        <Text style={{ fontSize: 12, color: colors.muted }} numberOfLines={1}>{[l.MANUFACTURER, l.DESCRIPTION].filter(Boolean).join('  ·  ')}</Text>
      </View>) },
    { key: 'code', title: 'Material code', flex: 1.2, render: (l) => (
      <View style={{ gap: 2 }}>
        <Text style={{ fontFamily: font.mono, fontSize: 12, color: colors.text }} numberOfLines={1}>{l.CATALOG_KEY || '—'}</Text>
        <Text style={{ fontFamily: font.mono, fontSize: 11, color: colors.muted }} numberOfLines={1}>{l.MANUFACTURER_PN || ''}</Text>
      </View>) },
    { key: 'cat', title: 'Category', flex: 1.1, render: (l) => <View style={{ gap: 2 }}><Text style={{ fontSize: 12.5, color: colors.text }} numberOfLines={1}>{l.CATEGORY || '—'}</Text><Text style={{ fontSize: 11.5, color: colors.muted }} numberOfLines={1}>{l.SUBCATEGORY || ''}</Text></View> },
    { key: 'sec', title: 'Sector', width: 76, render: (l) => <Text style={{ fontSize: 12.5, color: colors.text }}>{l.SECTOR === 'SITE' || !l.SECTOR ? 'Site' : l.SECTOR}</Text> },
    { key: 'qty', title: 'Quantity', width: 96, align: 'right', render: (l) => (
      <View style={{ alignItems: 'flex-end' }}>
        <Text style={{ fontSize: 14, fontWeight: '600', color: colors.text }}>{num(l.TOTAL_QTY)} <Text style={{ fontSize: 11, color: colors.muted, fontWeight: '400' }}>{l.UOM || 'EA'}</Text></Text>
      </View>) },
    { key: 'act', title: 'Action', width: 90, render: (l) => <Badge text={l.ACTION} color={l.ACTION === 'Install' ? colors.ok : l.ACTION === 'Remove' ? colors.danger : colors.neutral} /> },
    { key: 'rule', title: 'Rule', width: 96, render: (l) => l.RULE_ID ? <Text style={{ fontFamily: font.mono, fontSize: 12, color: colors.accent }}>{l.RULE_ID}</Text> : <Text style={{ color: colors.faint }}>—</Text> },
    { key: 'calc', title: 'Calculation', flex: 2, render: (l) => <Text style={{ fontSize: 12, color: colors.muted, lineHeight: 17 }} numberOfLines={2}>{calc(l) || '—'}</Text> },
    { key: 'st', title: 'Status', width: 150, render: (l) => needsReview(l)
      ? <View style={{ gap: 2 }}><Badge text="Needs review" color={colors.warn} dot /><Text style={{ fontSize: 11, color: colors.muted }} numberOfLines={2}>{String(l.STATUS).replace(/^Review:\s*/i, '')}</Text></View>
      : <Badge text="Rule applied" color={colors.ok} dot /> },
  ];

  return (
    <View>
      <Card padded={false}>
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: space(4), flexWrap: 'wrap', padding: space(5) }}>
          <View style={{ flexShrink: 1, minWidth: 260 }}>
            <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>Bill of materials</Text>
            <Text style={[s.muted, { marginTop: 4 }]}>
              {summary.revision ? `Generated with rulebook ${summary.revision}` : `Generated for ${siteId}`}{d.data.run_id ? `  ·  run ${d.data.run_id}` : ''}
            </Text>
            {file_name ? <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: space(2) }}><Icon name="file" size={13} color={colors.faint} /><Text style={{ fontFamily: font.mono, fontSize: 12, color: colors.muted }}>{file_name}</Text></View> : null}
          </View>
          {download_path ? <Button icon="download" title="Export to Excel" onPress={() => Linking.openURL(authedUrl(download_path))} /> : null}
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(3), paddingHorizontal: space(5), paddingBottom: space(5) }}>
          <Stat label="BOM lines" value={summary.lines ?? lines.length} icon="list" hint={`${rulesUsed.size} rules applied`} />
          <Stat label="Install" value={summary.install_lines ?? 0} icon="plus-circle" color={colors.ok} hint={`${num(summary.install_qty)} units`} />
          <Stat label="Remove" value={summary.remove_lines ?? 0} icon="minus-circle" color={summary.remove_lines ? colors.danger : undefined} hint={`${num(summary.remove_qty)} units`} />
          <Stat label="Needs review" value={review} icon="eye" color={review ? colors.warn : undefined} hint={review ? 'Check before export' : 'Nothing to check'} />
          <Stat label="Rules not applied" value={notApplied.length} icon="slash" color={notApplied.length ? colors.danger : undefined} hint={notApplied.length ? 'See the list below' : 'Every rule was applied'} />
          {summary.total_material_cost ? <Stat label="Material cost" value={money(summary.total_material_cost)} icon="dollar-sign" hint="Install lines" /> : null}
        </View>
      </Card>

      {notApplied.length ? (
        <Banner kind="danger" icon="slash" title={`${notApplied.length} rule${notApplied.length === 1 ? ' was' : 's were'} not applied`}>
          <View style={{ gap: 4, marginTop: 2 }}>
            {notApplied.map((i, k) => (
              <Text key={k} style={{ fontSize: 12.5, color: colors.text, lineHeight: 18 }}>
                <Text style={{ fontFamily: font.mono, fontWeight: '600' }}>{i.rule_id || i.RULE_ID || '—'}</Text>{'  '}{String(i.message ?? i.MESSAGE ?? '').replace(/^\S+ is not applied:\s*/, '')}
              </Text>
            ))}
            <Text style={{ fontSize: 12, color: colors.muted, marginTop: 4 }}>These rules did not add any line. Correct the rule in the BOM rules workbook, then run the pipeline again.</Text>
          </View>
        </Banner>
      ) : null}

      <Tabs value={view} onChange={setView} style={{ marginTop: space(2), marginBottom: space(4) }}
        tabs={[{ key: 'lines', label: 'BOM lines', icon: 'list', count: lines.length }, { key: 'workbook', label: 'Export preview', icon: 'grid', count: sheets.length },
          { key: 'issues', label: 'Issues', icon: 'alert-triangle', count: issues.length }]} />

      {view !== 'issues' ? (
        <View style={{ flexDirection: 'row', gap: space(3), alignItems: 'center', flexWrap: 'wrap', marginBottom: space(3) }}>
          <SearchBox value={query} onChangeText={setQuery} placeholder="Search model, code, P/N, description or rule" style={{ flex: 1, minWidth: 260 }} />
          {view === 'lines' ? (
            <Chips value={filter} onChange={setFilter} options={[
              { key: 'ALL', label: 'All', count: lines.length }, { key: 'Install', label: 'Install', count: summary.install_lines ?? 0 },
              { key: 'Remove', label: 'Remove', count: summary.remove_lines ?? 0 }, { key: 'REVIEW', label: 'Needs review', count: review }]} />
          ) : sheets.length > 1 ? (
            <Chips value={String(sheetIdx)} onChange={(v) => setSheetIdx(Number(v))} options={sheets.map((sh, i) => ({ key: String(i), label: sh.name, count: sh.rows.length }))} />
          ) : null}
        </View>
      ) : null}

      {view === 'lines' ? (
        <DataTable columns={columns} rows={filtered} keyFor={(l, i) => String(l.LINE_ID ?? i)} minWidth={1180}
          empty={<EmptyState icon="search" title="No lines match" text="Change the search or the filter." />} />
      ) : view === 'workbook' && sheet ? (
        <WorkbookGrid sheet={sheet} query={query} />
      ) : (
        <DataTable rows={[...notApplied, ...otherIssues]} keyFor={(_, i) => String(i)} minWidth={820}
          empty={<EmptyState icon="check-circle" title="No issues" text="The BOM engine raised no issues for this run." />}
          columns={[
            { key: 'sev', title: 'Severity', width: 110, render: (i) => <Badge text={String(i.severity ?? i.SEVERITY ?? '')} dot /> },
            { key: 'code', title: 'Code', width: 210, render: (i) => <Text style={{ fontFamily: font.mono, fontSize: 12, color: colors.text }} numberOfLines={1}>{i.code ?? i.CODE}</Text> },
            { key: 'rule', title: 'Rule', width: 100, render: (i) => <Text style={{ fontFamily: font.mono, fontSize: 12, color: colors.accent }}>{i.rule_id || i.RULE_ID || '—'}</Text> },
            { key: 'msg', title: 'Message', flex: 3, render: (i) => <Text style={{ fontSize: 12.5, color: colors.text, lineHeight: 18 }}>{show(i.message ?? i.MESSAGE)}</Text> },
          ]} />
      )}
      <Text style={[s.muted, { fontSize: 12, marginTop: space(2) }]}>
        {view === 'lines' ? `Showing ${filtered.length} of ${lines.length} lines` : view === 'workbook' && sheet ? `Sheet "${sheet.name}" as it appears in the exported workbook` : `${issues.length} issue${issues.length === 1 ? '' : 's'}`}
      </Text>
    </View>
  );
}
