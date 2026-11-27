// Extraction results for stage 2 (construction drawing + drone survey) and stage 5 (RFDS + MA/SA), in one visual language:
// a compact summary, one card per source, and a split workspace (source document on the left, extracted values on the right).
import { Feather } from '@expo/vector-icons';
import React, { useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { Row } from '../../../lib/types';
import { useApi } from '../../../lib/useApi';
import { PipelineRun, PipelineStep } from '../../../lib/types';
import { SourcePreview } from '../../FilePreviewModal';
import { colors, font, radius, space, tint } from '../../theme';
import { Banner, Button, Chips, EmptyState, IconName, SearchBox } from '../../ui';
import { duration } from '../StageTimeline';
import { CATEGORY_ICON, CATEGORY_ORDER, FIELD_STATUS, FieldStatus, stage2Cards, stage5Cards, XCard, XDocument, XField } from './model';

// ------------------------------------------------------------------ small parts
export function ExtractionStatusBadge({ status, compact }: { status: FieldStatus; compact?: boolean }) {
  const v = FIELD_STATUS[status];
  return (
    <View accessibilityLabel={v.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: compact ? 6 : 8, height: compact ? 20 : 22, borderRadius: 6, backgroundColor: v.bg, borderWidth: 1, borderColor: v.line, alignSelf: 'flex-start' }}>
      <Feather name={v.icon} size={compact ? 11 : 12} color={v.color} />
      <Text style={{ fontSize: compact ? 11 : 11.5, fontWeight: '600', color: v.color }}>{v.label}</Text>
    </View>
  );
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <View style={{ flexGrow: 1, flexBasis: 140, paddingHorizontal: space(3.5), paddingVertical: space(3), borderRadius: 12, backgroundColor: '#fff', borderWidth: 1, borderColor: colors.border }}>
      <Text style={{ fontSize: 12, color: colors.muted }}>{label}</Text>
      <Text style={{ fontSize: 19, fontWeight: '600', color: tone ?? colors.text, marginTop: 3, letterSpacing: -0.3 }}>{value}</Text>
    </View>
  );
}

export function ExtractionSummary({ title, step, cards }: { title: string; step: PipelineStep; cards: XCard[] }) {
  const all = cards.flatMap((c) => c.fields);
  const review = all.filter((f) => f.status === 'REVIEW').length;
  const docs = cards.reduce((a, c) => a + c.documents.filter((d) => d.status !== 'SUPERSEDED').length, 0);
  const st = step.status === 'DONE' ? (review ? FIELD_STATUS.REVIEW : { label: 'Completed', color: '#0F766E' }) : step.status === 'FAILED' ? FIELD_STATUS.FAILED : step.status === 'SKIPPED' ? { label: 'Skipped', color: '#64748B' } : { label: step.status, color: colors.info };
  return (
    <View style={{ marginBottom: space(4) }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(3), marginBottom: space(3), flexWrap: 'wrap' }}>
        <View style={{ width: 32, height: 32, borderRadius: 9, backgroundColor: tint.info.bg, alignItems: 'center', justifyContent: 'center' }}><Feather name="cpu" size={16} color={colors.accent} /></View>
        <View style={{ flex: 1, minWidth: 200 }}>
          <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text }}>{title}</Text>
          <Text style={{ fontSize: 12.5, color: colors.muted }}>{cards.map((c) => c.title).join(' and ')}{step.duration_ms != null ? `  ·  ${duration(step.duration_ms)}` : ''}</Text>
        </View>
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(2.5) }}>
        <Metric label="Stage status" value={st.label} tone={st.color} />
        <Metric label="Source documents" value={docs} />
        <Metric label="Extracted values" value={all.length} />
        <Metric label="Need review" value={review} tone={review ? FIELD_STATUS.REVIEW.color : undefined} />
      </View>
    </View>
  );
}

export function ExtractionDocumentCard({ card, selected, onOpen }: { card: XCard; selected: boolean; onOpen: () => void }) {
  const v = FIELD_STATUS[card.status];
  const disabled = card.status === 'MISSING';
  return (
    <Pressable onPress={onOpen} disabled={disabled} accessibilityRole="button" accessibilityState={{ selected, disabled }} accessibilityLabel={`${card.title}, ${v.label}. View details`}
      style={({ hovered }: any) => [{ flexGrow: 1, flexBasis: 320, minWidth: 0, borderRadius: 14, borderWidth: 1, padding: space(4), backgroundColor: selected ? '#F5F8FF' : '#fff',
        borderColor: selected ? colors.accent : hovered && !disabled ? colors.borderStrong : colors.border, opacity: disabled ? 0.75 : 1 },
        selected ? ({ boxShadow: '0 0 0 3px rgba(37,99,235,0.12)' } as any) : hovered && !disabled ? ({ boxShadow: '0 4px 14px rgba(16,24,40,0.07)' } as any) : null]}>
      <View style={{ flexDirection: 'row', gap: space(3), alignItems: 'flex-start' }}>
        <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: v.bg, borderWidth: 1, borderColor: v.line, alignItems: 'center', justifyContent: 'center' }}>
          <Feather name={card.icon} size={18} color={v.color} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={{ fontSize: 14.5, fontWeight: '600', color: colors.text }}>{card.title}</Text>
          <Text style={{ fontSize: 12.5, color: colors.muted, marginTop: 2, fontFamily: font.mono }} numberOfLines={1}>{card.primary?.name ?? 'No file'}</Text>
        </View>
        <ExtractionStatusBadge status={card.status} />
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: space(3) }}>
        {card.primary?.format ? <Fact icon="file" text={card.primary.format} /> : null}
        {card.method ? <Fact icon="tool" text={card.method} /> : null}
        {card.documents.length > 1 ? <Fact icon="layers" text={`${card.documents.length} files`} /> : null}
      </View>
      <Text style={{ fontSize: 12.5, color: colors.text, marginTop: space(3), lineHeight: 18 }}>{card.statusNote ?? card.summary.join('  ·  ')}</Text>
      {!disabled ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: space(3) }}>
          <Text style={{ fontSize: 12.5, fontWeight: '600', color: colors.accent }}>{selected ? 'Viewing details' : 'View details'}</Text>
          <Feather name={selected ? 'chevron-down' : 'arrow-right'} size={14} color={colors.accent} />
        </View>
      ) : null}
    </Pressable>
  );
}
const Fact = ({ icon, text }: { icon: IconName; text: string }) => (
  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 8, height: 22, borderRadius: 6, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border }}>
    <Feather name={icon} size={11} color={colors.muted} /><Text style={{ fontSize: 11.5, color: colors.muted }} numberOfLines={1}>{text}</Text>
  </View>
);

export function ExtractedFieldCard({ f, active, onPress }: { f: XField; active: boolean; onPress?: () => void }) {
  const v = FIELD_STATUS[f.status];
  return (
    <Pressable onPress={onPress} disabled={!onPress} accessibilityRole="button" accessibilityLabel={`${f.label}: ${f.value}. ${v.label}${f.whereLabel ? `. Show in source, ${f.whereLabel}` : ''}`}
      style={({ hovered }: any) => [{ flexDirection: 'row', gap: space(3), padding: space(3), borderRadius: 10, borderWidth: 1,
        backgroundColor: active ? '#F5F8FF' : '#fff', borderColor: active ? colors.accent : hovered && onPress ? colors.borderStrong : colors.border }]}>
      <View style={{ width: 3, alignSelf: 'stretch', borderRadius: 2, backgroundColor: v.color, opacity: f.status === 'EXTRACTED' ? 0.35 : 1 }} />
      <View style={{ flex: 1, minWidth: 0, gap: 3 }}>
        <Text style={{ fontSize: 11.5, color: colors.muted }} numberOfLines={1}>{f.label}</Text>
        <Text style={{ fontSize: 13.5, fontWeight: '600', color: colors.text }} numberOfLines={2} selectable={!onPress}>{f.value || '—'}</Text>
        {f.detail ? <Text style={{ fontSize: 12, color: colors.muted, lineHeight: 17 }} numberOfLines={2}>{f.detail}</Text> : null}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 3, flexWrap: 'wrap' }}>
          <ExtractionStatusBadge status={f.status} compact />
          {f.confidence != null && !Number.isNaN(f.confidence) ? <Text style={{ fontSize: 11.5, color: colors.muted }}>{`${Math.round(f.confidence * 100)}% confidence`}</Text> : null}
          {f.whereLabel ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <Feather name="crosshair" size={11} color={onPress ? colors.accent : colors.faint} />
              <Text style={{ fontSize: 11.5, color: onPress ? colors.accent : colors.faint }}>{f.whereLabel}</Text>
            </View>
          ) : null}
          {f.method ? <Text style={{ fontSize: 11, color: colors.faint, fontFamily: font.mono }}>{f.method}</Text> : null}
        </View>
      </View>
    </Pressable>
  );
}

export function ExtractionCategorySection({ title, fields, open, onToggle, activeId, onField }: {
  title: string; fields: XField[]; open: boolean; onToggle: () => void; activeId: string | null; onField: (f: XField) => void;
}) {
  const review = fields.filter((f) => f.status === 'REVIEW').length;
  return (
    <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, backgroundColor: '#fff', overflow: 'hidden' }}>
      <Pressable onPress={onToggle} accessibilityRole="button" accessibilityState={{ expanded: open }}
        style={({ hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: space(3.5), paddingVertical: space(3), backgroundColor: hovered ? colors.surfaceAlt : '#fff' })}>
        <Feather name={CATEGORY_ICON[title] ?? 'folder'} size={15} color={colors.accent} />
        <Text style={{ flex: 1, fontSize: 13.5, fontWeight: '600', color: colors.text }}>{title}</Text>
        {review ? <ExtractionStatusBadge status="REVIEW" compact /> : null}
        <Text style={{ fontSize: 11.5, fontWeight: '600', color: colors.muted, backgroundColor: colors.surfaceAlt, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4 }}>{fields.length}</Text>
        <Feather name={open ? 'chevron-up' : 'chevron-down'} size={15} color={colors.faint} />
      </Pressable>
      {open ? (
        <View style={{ padding: space(3), paddingTop: 0, gap: space(2) }}>
          {fields.map((f) => <ExtractedFieldCard key={f.id} f={f} active={f.id === activeId} onPress={f.docId ? () => onField(f) : undefined} />)}
        </View>
      ) : null}
    </View>
  );
}

// ------------------------------------------------------------------ workspace
type Filter = 'ALL' | 'REVIEW' | 'EXTRACTED' | 'VERIFIED';

export function ExtractionWorkspace({ card, onClose, wide }: { card: XCard; onClose: () => void; wide: boolean }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('ALL');
  const [active, setActive] = useState<XField | null>(null);
  const [file, setFile] = useState<XDocument | undefined>(card.primary);
  const [previewOpen, setPreviewOpen] = useState(true);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return card.fields.filter((f) => (filter === 'ALL' || f.status === filter) && (!q || `${f.label} ${f.value} ${f.detail ?? ''} ${f.category}`.toLowerCase().includes(q)));
  }, [card.fields, query, filter]);
  const groups = useMemo(() => {
    const m = new Map<string, XField[]>();
    for (const f of visible) m.set(f.category, [...(m.get(f.category) ?? []), f]);
    return [...m.entries()].sort((a, b) => (CATEGORY_ORDER.indexOf(a[0]) + 99) % 199 - (CATEGORY_ORDER.indexOf(b[0]) + 99) % 199);
  }, [visible]);
  const count = (s: Filter) => (s === 'ALL' ? card.fields.length : card.fields.filter((f) => f.status === s).length);

  const pick = (f: XField) => {
    setActive(f);
    const doc = card.documents.find((d) => d.docId === f.docId);
    if (doc) setFile(doc);
    setPreviewOpen(true);
  };

  const source = (
    <View style={{ flex: wide ? 1.1 : undefined, minWidth: 0, borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: '#fff', overflow: 'hidden' }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: space(4), paddingVertical: space(3), borderBottomWidth: previewOpen ? 1 : 0, borderBottomColor: colors.border, flexWrap: 'wrap' }}>
        <Feather name="file-text" size={15} color={colors.accent} />
        <Text style={{ fontSize: 13.5, fontWeight: '600', color: colors.text }}>Source document</Text>
        {active?.whereLabel ? <Text style={{ fontSize: 12, color: colors.accent }}>{`Showing ${active.whereLabel}`}</Text> : null}
        <View style={{ flex: 1 }} />
        {!wide ? <Button small kind="ghost" title={previewOpen ? 'Hide' : 'Show'} iconRight={previewOpen ? 'chevron-up' : 'chevron-down'} onPress={() => setPreviewOpen((o) => !o)} /> : null}
      </View>
      {previewOpen ? (
        <>
          {card.documents.length > 1 ? (
            <View style={{ paddingHorizontal: space(3), paddingTop: space(2) }}>
              <Chips value={file?.docId ?? file?.name ?? ''} onChange={(k) => { setFile(card.documents.find((d) => (d.docId ?? d.name) === k)); setActive(null); }}
                options={card.documents.map((d) => ({ key: d.docId ?? d.name, label: `${d.name}${d.status === 'SUPERSEDED' ? ' (superseded)' : ''}` }))} />
            </View>
          ) : null}
          <View style={{ padding: space(3) }}>
            {file?.docId ? <SourcePreview key={file.docId} target={{ name: file.name, docId: file.docId }} focus={active && active.docId === file.docId ? active.where ?? undefined : undefined} height={wide ? 680 : 460} />
              : <EmptyState icon="file" title="No preview for this file" text="The document is not registered for this run, so it cannot be opened here." />}
          </View>
        </>
      ) : null}
    </View>
  );

  const data = (
    <View style={{ flex: wide ? 1 : undefined, minWidth: 0, gap: space(3) }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <Feather name="cpu" size={15} color={colors.accent} />
        <Text style={{ flex: 1, fontSize: 13.5, fontWeight: '600', color: colors.text }}>Extracted data</Text>
        <Button small kind="ghost" icon="x" title="Close" onPress={onClose} />
      </View>
      <SearchBox value={query} onChangeText={setQuery} placeholder="Search extracted values" />
      <Chips<Filter> value={filter} onChange={setFilter} options={[
        { key: 'ALL', label: 'All', count: count('ALL') }, { key: 'REVIEW', label: 'Needs review', count: count('REVIEW') },
        { key: 'EXTRACTED', label: 'Extracted', count: count('EXTRACTED') }, { key: 'VERIFIED', label: 'Verified', count: count('VERIFIED') }]} />
      {card.issues.length ? <Banner kind="danger" title="Reader problems">{card.issues.join('\n')}</Banner> : null}
      {groups.length === 0 ? (
        <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, backgroundColor: '#fff' }}>
          <EmptyState icon="search" title={card.fields.length ? 'No values match' : 'No values were extracted'} text={card.fields.length ? 'Change the search or the status filter.' : card.statusNote ?? 'The API returned no field values for this document.'} />
        </View>
      ) : groups.map(([cat, fs]) => (
        <ExtractionCategorySection key={cat} title={cat} fields={fs} open={!collapsed[cat]} onToggle={() => setCollapsed((c) => ({ ...c, [cat]: !c[cat] }))} activeId={active?.id ?? null} onField={pick} />
      ))}
      <Text style={{ fontSize: 11.5, color: colors.faint }}>Select a value with a location to show it in the source document. "Verified" appears only after a person has reviewed the value.</Text>
    </View>
  );

  return (
    <View style={{ marginTop: space(4), padding: space(4), borderRadius: 16, backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: space(4) }}>
        <Feather name={card.icon} size={16} color={colors.text} />
        <Text style={{ fontSize: 15, fontWeight: '600', color: colors.text }}>{card.title}</Text>
        <ExtractionStatusBadge status={card.status} />
      </View>
      <View style={{ flexDirection: wide ? 'row' : 'column', gap: space(4), alignItems: wide ? 'flex-start' : 'stretch' }}>
        {source}
        {data}
      </View>
    </View>
  );
}

// ------------------------------------------------------------------ the stage views
export function ExtractionStage({ run, step, x, siteId, wide }: { run: PipelineRun; step: PipelineStep; x: any; siteId: string; wide: boolean }) {
  const isDesign = step.key === 'DESIGN';
  const ingest = useApi<any>(isDesign && step.status === 'DONE' ? `/pipeline/runs/${run.RUN_ID}/steps/INGEST` : null);
  const docIndex = useMemo(() => Object.fromEntries(((ingest.data?.documents ?? []) as Row[]).map((d) => [d.FILE_NAME, d])), [ingest.data]);
  const cards = useMemo(() => (isDesign ? stage5Cards(x, docIndex) : stage2Cards(x, step.status)), [isDesign, x, docIndex, step.status]);
  const [open, setOpen] = useState<XCard['key'] | null>(null);
  const card = cards.find((c) => c.key === open) ?? null;

  if (isDesign && (step.status === 'SKIPPED' || x?.skipped)) {
    return <Banner kind="warn" title="Stage 5 was skipped">{step.message || x?.reason || 'Open redlines or RFIs from stages 3 and 4 have to be resolved first.'}</Banner>;
  }
  return (
    <View>
      <ExtractionSummary title={isDesign ? 'Extract RFDS & MA/SA' : 'Extract values'} step={step} cards={cards} />
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space(3) }}>
        {cards.map((c) => <ExtractionDocumentCard key={c.key} card={c} selected={open === c.key} onOpen={() => setOpen(open === c.key ? null : c.key)} />)}
      </View>
      {card ? <ExtractionWorkspace key={card.key} card={card} wide={wide} onClose={() => setOpen(null)} /> : null}
      {isDesign && cards.find((c) => c.key === 'MA_SA')?.fields.length === 0 && cards.find((c) => c.key === 'MA_SA')?.status !== 'MISSING' ? (
        <Text style={{ fontSize: 12, color: colors.faint, marginTop: space(3) }}>The MA/SA report shows its value count and analysis result; the API does not return its individual values.</Text>
      ) : null}
    </View>
  );
}
