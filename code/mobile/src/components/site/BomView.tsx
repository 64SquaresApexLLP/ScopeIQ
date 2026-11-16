import React, { useMemo, useState } from 'react';
import { Linking, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { authedUrl } from '../../lib/api';
import { num } from '../../lib/format';
import { useApi } from '../../lib/useApi';
import { colors, space } from '../theme';
import { Badge, Button, Card, Empty, ErrorView, Icon, IconBadge, Loading, Muted, Row, s, Title } from '../ui';

interface BomSheet {
  name: string;
  columns: string[];
  rows: (string | number | boolean | null)[][];
}

interface BomPreviewResponse {
  available: boolean;
  site_id: string;
  run_id: string | null;
  file_name: string | null;
  download_path: string | null;
  summary: {
    lines?: number;
    install_lines?: number;
    remove_lines?: number;
    install_qty?: number;
    remove_qty?: number;
    needs_review?: number;
    issues_count?: number;
    total_material_cost?: number;
    revision?: string | null;
  };
  sheets: BomSheet[];
  lines: Record<string, any>[];
  issues: Record<string, any>[];
}

type ViewMode = 'excel' | 'table';
type ActionFilter = 'ALL' | 'Install' | 'Remove';

const COL_WIDTHS: Record<string, number> = {
  'Site ID': 84,
  Market: 68,
  Sector: 76,
  Technology: 86,
  Band: 84,
  'Equipment Category': 148,
  Manufacturer: 112,
  Model: 164,
  'Manufacturer P/N': 140,
  'Customer P/N': 110,
  Description: 290,
  UOM: 56,
  'Design Qty': 84,
  'Spare Qty': 80,
  'Total Qty': 80,
  'Unit Cost ($)': 108,
  'Total Cost ($)': 114,
  'Supply (CFM/VFM)': 120,
  Action: 88,
  Source: 160,
  Drawing: 115,
  'BOM Rule': 86,
  Revision: 150,
  Status: 185,
  Severity: 85,
  Code: 160,
  Rule: 85,
  Message: 480,
};

const NUMERIC_COLS = new Set(['Design Qty', 'Spare Qty', 'Total Qty']);
const CURRENCY_COLS = new Set(['Unit Cost ($)', 'Total Cost ($)']);

function formatCurrency(val: number): string {
  return `$${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function colWidth(name: string): number {
  return COL_WIDTHS[name] ?? 125;
}

function formatCell(val: string | number | boolean | null | undefined, colName: string): string {
  if (val === null || val === undefined || val === '') return '—';
  if (typeof val === 'number') {
    if (CURRENCY_COLS.has(colName)) return formatCurrency(val);
    if (NUMERIC_COLS.has(colName)) return num(val);
  }
  return String(val);
}

function ExcelGrid({ sheet, query, actionFilter }: { sheet: BomSheet; query: string; actionFilter: ActionFilter }) {
  const actionColIdx = sheet.columns.findIndex((c) => c.toLowerCase() === 'action');
  const statusColIdx = sheet.columns.findIndex((c) => c.toLowerCase() === 'status');

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sheet.rows.filter((row) => {
      if (actionFilter !== 'ALL' && actionColIdx >= 0) {
        if (String(row[actionColIdx] ?? '').toLowerCase() !== actionFilter.toLowerCase()) return false;
      }
      if (!q) return true;
      return row.some((cell) => cell !== null && cell !== undefined && String(cell).toLowerCase().includes(q));
    });
  }, [sheet.rows, query, actionFilter, actionColIdx]);

  const rowIndexWidth = 46;
  const totalWidth = rowIndexWidth + sheet.columns.reduce((acc, c) => acc + colWidth(c), 0);

  return (
    <View style={{ borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 10, overflow: 'hidden', backgroundColor: '#fff' }}>
      <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{ width: totalWidth }}>
          {/* Excel Header Row */}
          <View style={{ flexDirection: 'row', backgroundColor: '#1F3864', borderBottomWidth: 2, borderBottomColor: '#0F2A5F' }}>
            <View style={{ width: rowIndexWidth, paddingVertical: 9, paddingHorizontal: 6, borderRightWidth: 1, borderRightColor: 'rgba(255,255,255,0.18)', alignItems: 'center', justifyContent: 'center' }}>
              <Text style={{ color: 'rgba(255,255,255,0.75)', fontSize: 11, fontWeight: '700' }}>#</Text>
            </View>
            {sheet.columns.map((c, idx) => (
              <View
                key={`${c}-${idx}`}
                style={{
                  width: colWidth(c),
                  paddingVertical: 9,
                  paddingHorizontal: 8,
                  borderRightWidth: idx < sheet.columns.length - 1 ? 1 : 0,
                  borderRightColor: 'rgba(255,255,255,0.16)',
                  justifyContent: 'center',
                }}
              >
                <Text style={{ color: '#fff', fontSize: 11.5, fontWeight: '700', textAlign: NUMERIC_COLS.has(c) ? 'right' : 'left' }} numberOfLines={1}>
                  {c}
                </Text>
              </View>
            ))}
          </View>

          {/* Excel Rows */}
          {filteredRows.length === 0 ? (
            <View style={{ padding: space(5), alignItems: 'flex-start' }}>
              <Muted>No rows match the current filter.</Muted>
            </View>
          ) : (
            filteredRows.map((row, rIdx) => {
              const statusVal = statusColIdx >= 0 ? String(row[statusColIdx] ?? '') : '';
              const needsReview = /review|not in/i.test(statusVal);
              const bg = needsReview ? '#FFFBEB' : rIdx % 2 === 1 ? '#F8FAFC' : '#FFFFFF';

              return (
                <View
                  key={rIdx}
                  style={{
                    flexDirection: 'row',
                    backgroundColor: bg,
                    borderBottomWidth: rIdx < filteredRows.length - 1 ? 1 : 0,
                    borderBottomColor: '#E2E8F0',
                  }}
                >
                  <View style={{ width: rowIndexWidth, paddingVertical: 7, paddingHorizontal: 6, backgroundColor: '#F1F5F9', borderRightWidth: 1, borderRightColor: '#E2E8F0', alignItems: 'center', justifyContent: 'center' }}>
                    <Text style={{ color: colors.muted, fontSize: 11, fontWeight: '600' }}>{rIdx + 1}</Text>
                  </View>
                  {sheet.columns.map((c, cIdx) => {
                    const raw = row[cIdx];
                    const isAction = c.toLowerCase() === 'action';
                    const isTotal = c === 'Total Qty';
                    const actStr = String(raw ?? '');

                    return (
                      <View
                        key={cIdx}
                        style={{
                          width: colWidth(c),
                          paddingVertical: 7,
                          paddingHorizontal: 8,
                          borderRightWidth: cIdx < sheet.columns.length - 1 ? 1 : 0,
                          borderRightColor: '#E2E8F0',
                          justifyContent: 'center',
                          alignItems: (NUMERIC_COLS.has(c) || CURRENCY_COLS.has(c)) ? 'flex-end' : 'flex-start',
                        }}
                      >
                        {isAction && raw ? (
                          <Badge text={actStr} color={actStr === 'Install' ? colors.ok : actStr === 'Remove' ? colors.danger : colors.muted} />
                        ) : (
                          <Text
                            style={{
                              fontSize: 12,
                              color: isTotal ? colors.primary : colors.text,
                              fontWeight: isTotal ? '700' : '400',
                              textAlign: (NUMERIC_COLS.has(c) || CURRENCY_COLS.has(c)) ? 'right' : 'left',
                            }}
                            numberOfLines={2}
                          >
                            {formatCell(raw, c)}
                          </Text>
                        )}
                      </View>
                    );
                  })}
                </View>
              );
            })
          )}
        </View>
      </ScrollView>
    </View>
  );
}

function TableSummaryView({ lines, query, actionFilter }: { lines: Record<string, any>[]; query: string; actionFilter: ActionFilter }) {
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return lines.filter((l) => {
      if (actionFilter !== 'ALL' && String(l.ACTION ?? '').toLowerCase() !== actionFilter.toLowerCase()) return false;
      if (!q) return true;
      return [l.SECTOR, l.CATEGORY, l.MANUFACTURER, l.MODEL, l.MANUFACTURER_PN, l.DESCRIPTION, l.RULE_ID, l.STATUS]
        .some((v) => v != null && String(v).toLowerCase().includes(q));
    });
  }, [lines, query, actionFilter]);

  const bySector = useMemo(() => {
    const map = new Map<string, Record<string, any>[]>();
    for (const l of filtered) {
      const sec = l.SECTOR || 'SITE';
      map.set(sec, [...(map.get(sec) ?? []), l]);
    }
    return [...map.entries()];
  }, [filtered]);

  if (!filtered.length) {
    return (
      <Card>
        <Muted>No BOM lines match the current filter.</Muted>
      </Card>
    );
  }

  return (
    <View style={{ gap: space(3) }}>
      {bySector.map(([sector, rows]) => (
        <Card key={sector} style={{ padding: 0, overflow: 'hidden' }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: space(4), paddingVertical: space(3), backgroundColor: '#F8FAFF', borderBottomWidth: 1, borderBottomColor: colors.border }}>
            <Text style={{ fontSize: 14, fontWeight: '800', color: colors.primary }}>
              {sector === 'SITE' ? 'Site-Wide' : `Sector ${sector}`}
            </Text>
            <Badge text={`${rows.length} line${rows.length === 1 ? '' : 's'}`} color={colors.accent} />
          </View>
          {rows.map((l, idx) => (
            <View
              key={l.LINE_ID ?? idx}
              style={{
                paddingHorizontal: space(4),
                paddingVertical: space(3),
                borderBottomWidth: idx < rows.length - 1 ? 1 : 0,
                borderBottomColor: colors.border,
                backgroundColor: /review|not in/i.test(String(l.STATUS ?? '')) ? '#FFFBEB' : '#fff',
              }}
            >
              <Row style={{ justifyContent: 'space-between', alignItems: 'flex-start', gap: space(2) }}>
                <View style={{ flex: 1, minWidth: 200 }}>
                  <Row style={{ alignItems: 'center', gap: space(1.5), flexWrap: 'wrap' }}>
                    <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text }}>{l.MODEL || l.CATALOG_KEY}</Text>
                    {l.CATEGORY ? <Badge text={l.CATEGORY} color={colors.muted} /> : null}
                    {l.RULE_ID ? <Badge text={l.RULE_ID} color={colors.info} /> : null}
                  </Row>
                  <Muted style={{ marginTop: 2 }}>{[l.MANUFACTURER, l.MANUFACTURER_PN, l.DESCRIPTION].filter(Boolean).join(' · ')}</Muted>
                  <Row style={{ marginTop: 4, gap: space(2), flexWrap: 'wrap' }}>
                    {l.TECHNOLOGY ? <Muted style={{ fontSize: 11.5 }}>{`Tech: ${l.TECHNOLOGY}`}</Muted> : null}
                    {l.BAND ? <Muted style={{ fontSize: 11.5 }}>{`Band: ${l.BAND}`}</Muted> : null}
                    {l.SUPPLY ? <Muted style={{ fontSize: 11.5 }}>{`Supply: ${l.SUPPLY}`}</Muted> : null}
                    {l.SOURCE ? <Muted style={{ fontSize: 11.5 }}>{`Source: ${l.SOURCE}`}</Muted> : null}
                  </Row>
                </View>
                <View style={{ alignItems: 'flex-end', gap: 4 }}>
                  <Text style={{ fontSize: 15, fontWeight: '800', color: colors.primary }}>{`${num(l.TOTAL_QTY)} ${l.UOM || 'EA'}`}</Text>
                  <Muted style={{ fontSize: 11 }}>{`Design ${num(l.DESIGN_QTY)} + Spare ${num(l.SPARE_QTY)}`}</Muted>
                  {l.ACTION === 'Install' && l.TOTAL_COST_USD != null ? (
                    <Text style={{ fontSize: 12, fontWeight: '700', color: '#059669' }}>
                      {formatCurrency(Number(l.TOTAL_COST_USD))}
                      {l.UNIT_COST_USD ? ` (${formatCurrency(Number(l.UNIT_COST_USD))}/ea)` : ''}
                    </Text>
                  ) : null}
                  <Badge text={l.ACTION} color={l.ACTION === 'Install' ? colors.ok : colors.danger} />
                </View>
              </Row>
            </View>
          ))}
        </Card>
      ))}
    </View>
  );
}

export function BomView({ siteId }: { siteId: string }) {
  const d = useApi<BomPreviewResponse>(`/bom/sites/${siteId}/preview`);
  const [mode, setMode] = useState<ViewMode>('excel');
  const [sheetIdx, setSheetIdx] = useState(0);
  const [query, setQuery] = useState('');
  const [actionFilter, setActionFilter] = useState<ActionFilter>('ALL');

  if (d.error) return <ErrorView error={d.error} onRetry={d.reload} />;
  if (!d.data) return <Loading />;

  // Show nothing until the BOM is actually generated and available
  if (!d.data.available) {
    return <Empty text="No BOM available yet." />;
  }

  const { summary, sheets, lines, download_path, file_name, issues } = d.data;
  const activeSheet = sheets[sheetIdx] ?? sheets[0];

  return (
    <View style={{ gap: space(3) }}>
      {/* Header card */}
      <Card style={{ marginBottom: 0 }}>
        <Row style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: space(3) }}>
          <Row style={{ alignItems: 'center', gap: space(3), flex: 1, minWidth: 240 }}>
            <IconBadge name="table" color={colors.accent} size={42} />
            <View style={{ flex: 1 }}>
              <Row style={{ alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
                <Title style={{ fontSize: 17, fontWeight: '800' }}>Bill of Materials Preview</Title>
                {file_name ? <Badge text={file_name} color={colors.primary} /> : null}
              </Row>
              <Muted style={{ marginTop: 2 }}>
                {summary.revision ? `Generated using rules ${summary.revision}` : `Generated BOM for ${siteId}`}
              </Muted>
            </View>
          </Row>

          <Row style={{ gap: space(2), flexWrap: 'wrap' }}>
            {download_path ? (
              <Button
                small
                title="Download Excel (.xlsx)"
                onPress={() => Linking.openURL(authedUrl(download_path))}
              />
            ) : null}
          </Row>
        </Row>

        {/* Summary metrics */}
        <Row style={{ gap: space(1.5), flexWrap: 'wrap', marginTop: space(3) }}>
          <Badge text={`${summary.lines ?? lines.length} total lines`} color={colors.primary} />
          {summary.total_material_cost != null && summary.total_material_cost > 0 ? (
            <Badge text={`Total Material: ${formatCurrency(summary.total_material_cost)}`} color="#059669" />
          ) : null}
          <Badge text={`${summary.install_lines ?? 0} install (${num(summary.install_qty)} qty)`} color={colors.ok} />
          <Badge text={`${summary.remove_lines ?? 0} remove (${num(summary.remove_qty)} qty)`} color={colors.danger} />
          {(summary.needs_review ?? 0) > 0 ? (
            <Badge text={`${summary.needs_review} need review`} color={colors.warn} />
          ) : null}
          {issues.length > 0 ? (
            <Badge text={`${issues.length} issue${issues.length === 1 ? '' : 's'}`} color={colors.warn} />
          ) : null}
        </Row>
      </Card>

      {/* Toolbar: Mode toggle, sheet selector, search & action filter */}
      <Card style={{ marginBottom: 0, padding: space(3) }}>
        <Row style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: space(2) }}>
          {/* View mode switch */}
          <Row style={{ gap: space(1), backgroundColor: colors.bg, padding: 3, borderRadius: 10, borderWidth: 1, borderColor: colors.border }}>
            {([
              { key: 'excel', label: 'Excel Preview', icon: 'grid' },
              { key: 'table', label: 'Grouped Table', icon: 'list' },
            ] as const).map((m) => {
              const on = mode === m.key;
              return (
                <Pressable
                  key={m.key}
                  onPress={() => setMode(m.key)}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 6,
                    paddingHorizontal: space(3),
                    paddingVertical: 6,
                    borderRadius: 8,
                    backgroundColor: on ? '#fff' : 'transparent',
                  }}
                >
                  <Icon name={m.icon} size={13} color={on ? colors.accent : colors.muted} />
                  <Text style={{ fontSize: 12.5, fontWeight: on ? '700' : '500', color: on ? colors.text : colors.muted }}>{m.label}</Text>
                </Pressable>
              );
            })}
          </Row>

          {/* Action filter */}
          <Row style={{ gap: space(1) }}>
            {(['ALL', 'Install', 'Remove'] as ActionFilter[]).map((af) => {
              const on = actionFilter === af;
              return (
                <Pressable
                  key={af}
                  onPress={() => setActionFilter(af)}
                  style={{
                    paddingHorizontal: space(2.5),
                    paddingVertical: 5,
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: on ? colors.accent : colors.border,
                    backgroundColor: on ? colors.soft : '#fff',
                  }}
                >
                  <Text style={{ fontSize: 12, fontWeight: '600', color: on ? colors.accent : colors.muted }}>
                    {af === 'ALL' ? 'All Actions' : af}
                  </Text>
                </Pressable>
              );
            })}
          </Row>

          {/* Search box */}
          <TextInput
            style={[s.input, { minWidth: 220, flexGrow: 1, maxWidth: 320, paddingVertical: 6, fontSize: 13 }]}
            placeholder="Filter by model, P/N, description, rule..."
            value={query}
            onChangeText={setQuery}
          />
        </Row>

        {/* Workbook sheet tabs when in Excel mode */}
        {mode === 'excel' && sheets.length > 1 ? (
          <Row style={{ marginTop: space(2.5), paddingTop: space(2), borderTopWidth: 1, borderTopColor: colors.border, gap: space(1.5) }}>
            <Muted style={{ fontSize: 11.5, fontWeight: '700' }}>Sheets:</Muted>
            {sheets.map((sh, idx) => {
              const on = idx === sheetIdx;
              return (
                <Pressable
                  key={sh.name}
                  onPress={() => setSheetIdx(idx)}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 5,
                    paddingHorizontal: 10,
                    paddingVertical: 4,
                    borderRadius: 6,
                    backgroundColor: on ? '#1F3864' : colors.bg,
                    borderWidth: 1,
                    borderColor: on ? '#1F3864' : colors.border,
                  }}
                >
                  <Text style={{ fontSize: 12, fontWeight: '700', color: on ? '#fff' : colors.text }}>{sh.name}</Text>
                  <Text style={{ fontSize: 11, color: on ? 'rgba(255,255,255,0.75)' : colors.muted }}>({sh.rows.length})</Text>
                </Pressable>
              );
            })}
          </Row>
        ) : null}
      </Card>

      {/* Main Content */}
      {mode === 'excel' && activeSheet ? (
        <ExcelGrid sheet={activeSheet} query={query} actionFilter={actionFilter} />
      ) : (
        <TableSummaryView lines={lines} query={query} actionFilter={actionFilter} />
      )}
    </View>
  );
}
