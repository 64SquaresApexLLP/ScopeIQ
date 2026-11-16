import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { api, authedUrl } from '../lib/api';
import { colors, shadow, space } from './theme';
import { Badge, Button, Icon, IconBadge, IconName, Muted, Row } from './ui';

export interface FilePreviewTarget {
  name: string;
  folder?: string;
  siteId?: string;
  docId?: string;
  size?: number;
}

interface SpreadsheetSheet {
  name: string;
  columns: string[];
  rows: (string | number | boolean | null)[][];
  total_rows?: number;
}

export interface PointCloudObject {
  object_id: string;
  object_type: string;
  sector?: string | null;
  bearing_deg?: number | null;
  facing_az_deg?: number | null;
  center_height_ft?: number | null;
  dimensions_in?: number[] | null;
  confidence?: number;
  method?: string;
}

export interface PointCloudStats {
  total_points: number;
  rendered_points: number;
  equipment_objects: number;
  roof_z_m?: number;
  class_counts?: Record<string, number>;
}

export interface PdfPage {
  page_number: number;
  width: number;
  height: number;
  image: string;
}

interface PreviewData {
  file_name: string;
  format: string;
  doc_type?: string;
  size: number;
  modified?: string;
  download_url: string;
  type: 'spreadsheet' | 'pdf' | 'image' | 'video' | 'json' | 'text' | 'cad' | 'pointcloud' | 'binary';
  file_url?: string;
  sheets?: SpreadsheetSheet[];
  pages?: PdfPage[];
  total_pages?: number;
  content?: any;
  raw?: string;
  category?: string;
  note?: string;
  error?: string;
  points?: [number, number, number, number][];
  objects?: PointCloudObject[];
  stats?: PointCloudStats;
}

const kb = (n?: number) =>
  !n ? '' : n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;

const fileIcon = (name: string): IconName =>
  (/\.(jpe?g|png|tif|webp|gif)$/i.test(name)
    ? 'image'
    : /\.(mp4|mov|avi|webm)$/i.test(name)
    ? 'video'
    : /\.(xlsx|xls|csv)$/i.test(name)
    ? 'grid'
    : /\.(laz|las)$/i.test(name)
    ? 'box'
    : /\.(json|txt|log|yaml|yml)$/i.test(name)
    ? 'code'
    : 'file-text') as IconName;

function SpreadsheetViewer({ sheets }: { sheets: SpreadsheetSheet[] }) {
  const [activeSheetIdx, setActiveSheetIdx] = useState(0);
  const [query, setQuery] = useState('');

  const currentSheet = sheets[activeSheetIdx] || sheets[0];

  const filteredRows = useMemo(() => {
    if (!currentSheet || !currentSheet.rows) return [];
    const q = query.trim().toLowerCase();
    if (!q) return currentSheet.rows;
    return currentSheet.rows.filter((row) =>
      row.some((cell) => cell !== null && cell !== undefined && String(cell).toLowerCase().includes(q))
    );
  }, [currentSheet, query]);

  if (!currentSheet) {
    return (
      <View style={{ padding: space(6), alignItems: 'center' }}>
        <Muted>No spreadsheet data found.</Muted>
      </View>
    );
  }

  const rowIndexWidth = 46;
  const colWidth = 140;
  const totalWidth = rowIndexWidth + (currentSheet.columns?.length || 1) * colWidth;

  return (
    <View style={{ flex: 1, gap: space(3) }}>
      {/* Sheet Tabs & Search */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: space(2) }}>
        {sheets.length > 1 ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {sheets.map((s, idx) => {
              const active = idx === activeSheetIdx;
              return (
                <Pressable
                  key={s.name || idx}
                  onPress={() => setActiveSheetIdx(idx)}
                  style={{
                    paddingHorizontal: 12,
                    paddingVertical: 6,
                    borderRadius: 6,
                    backgroundColor: active ? '#1E3A8A' : '#F1F5F9',
                    borderWidth: 1,
                    borderColor: active ? '#1E3A8A' : '#CBD5E1',
                  }}
                >
                  <Text style={{ fontSize: 12, fontWeight: '700', color: active ? '#fff' : colors.text }}>
                    {s.name || `Sheet ${idx + 1}`} ({s.rows?.length || 0})
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
        ) : (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Icon name="grid" size={14} color={colors.accent} />
            <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }}>
              {currentSheet.name || 'Sheet'}
            </Text>
          </View>
        )}

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: space(2) }}>
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              backgroundColor: '#F8FAFC',
              borderWidth: 1,
              borderColor: '#CBD5E1',
              borderRadius: 8,
              paddingHorizontal: 10,
              paddingVertical: 5,
              width: 220,
            }}
          >
            <Icon name="search" size={13} color={colors.muted} />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search table..."
              placeholderTextColor={colors.muted}
              style={{ flex: 1, fontSize: 12, marginLeft: 6, outlineStyle: 'none' as any }}
            />
            {query ? (
              <Pressable onPress={() => setQuery('')}>
                <Icon name="x" size={13} color={colors.muted} />
              </Pressable>
            ) : null}
          </View>
          <Badge text={`${filteredRows.length} of ${currentSheet.rows?.length || 0} rows`} color={colors.accent} />
        </View>
      </View>

      {/* Excel Table Grid */}
      <View style={{ borderWidth: 1, borderColor: '#CBD5E1', borderRadius: 10, overflow: 'hidden', backgroundColor: '#fff', maxHeight: 540 }}>
        <ScrollView horizontal showsHorizontalScrollIndicator>
          <View style={{ width: Math.max(totalWidth, 700) }}>
            {/* Header */}
            <View style={{ flexDirection: 'row', backgroundColor: '#1F3864', borderBottomWidth: 2, borderBottomColor: '#0F2A5F' }}>
              <View style={{ width: rowIndexWidth, paddingVertical: 8, paddingHorizontal: 4, borderRightWidth: 1, borderRightColor: 'rgba(255,255,255,0.18)', alignItems: 'center', justifyContent: 'center' }}>
                <Text style={{ color: 'rgba(255,255,255,0.75)', fontSize: 11, fontWeight: '700' }}>#</Text>
              </View>
              {currentSheet.columns.map((c, idx) => (
                <View
                  key={`${c}-${idx}`}
                  style={{
                    width: colWidth,
                    paddingVertical: 8,
                    paddingHorizontal: 8,
                    borderRightWidth: idx < currentSheet.columns.length - 1 ? 1 : 0,
                    borderRightColor: 'rgba(255,255,255,0.16)',
                    justifyContent: 'center',
                  }}
                >
                  <Text style={{ color: '#fff', fontSize: 11.5, fontWeight: '700' }} numberOfLines={1}>
                    {c}
                  </Text>
                </View>
              ))}
            </View>

            {/* Rows */}
            <ScrollView style={{ maxHeight: 480 }} nestedScrollEnabled>
              {filteredRows.length === 0 ? (
                <View style={{ padding: space(5), alignItems: 'center' }}>
                  <Muted>No matching rows found.</Muted>
                </View>
              ) : (
                filteredRows.map((row, rIdx) => (
                  <View
                    key={rIdx}
                    style={{
                      flexDirection: 'row',
                      backgroundColor: rIdx % 2 === 1 ? '#F8FAFC' : '#FFFFFF',
                      borderBottomWidth: rIdx < filteredRows.length - 1 ? 1 : 0,
                      borderBottomColor: '#E2E8F0',
                    }}
                  >
                    <View style={{ width: rowIndexWidth, paddingVertical: 7, paddingHorizontal: 4, backgroundColor: '#F1F5F9', borderRightWidth: 1, borderRightColor: '#E2E8F0', alignItems: 'center', justifyContent: 'center' }}>
                      <Text style={{ color: colors.muted, fontSize: 11, fontWeight: '600' }}>{rIdx + 1}</Text>
                    </View>
                    {currentSheet.columns.map((_, cIdx) => {
                      const val = row[cIdx];
                      const str = val === null || val === undefined ? '' : String(val);
                      return (
                        <View
                          key={cIdx}
                          style={{
                            width: colWidth,
                            paddingVertical: 7,
                            paddingHorizontal: 8,
                            borderRightWidth: cIdx < currentSheet.columns.length - 1 ? 1 : 0,
                            borderRightColor: '#E2E8F0',
                            justifyContent: 'center',
                          }}
                        >
                          <Text style={{ fontSize: 12, color: colors.text }} numberOfLines={2}>
                            {str || '—'}
                          </Text>
                        </View>
                      );
                    })}
                  </View>
                ))
              )}
            </ScrollView>
          </View>
        </ScrollView>
      </View>
    </View>
  );
}

const CLASS_CONFIG: Record<number, { label: string; color: string; defaultShow: boolean; radius: number }> = {
  64: { label: 'Antennas', color: '#38BDF8', defaultShow: true, radius: 3.2 },
  65: { label: 'Remote Radios (RRU)', color: '#C084FC', defaultShow: true, radius: 2.8 },
  66: { label: 'Mount Pipes', color: '#FBBF24', defaultShow: true, radius: 2.2 },
  68: { label: 'Base Cabinets', color: '#34D399', defaultShow: true, radius: 2.5 },
  6: { label: 'Tower Structure', color: '#64748B', defaultShow: true, radius: 1.5 },
  2: { label: 'Ground Surface', color: '#84CC16', defaultShow: false, radius: 1.2 },
};

function PointCloudViewer({
  points = [],
  objects = [],
  stats,
}: {
  points?: [number, number, number, number][];
  objects?: PointCloudObject[];
  stats?: PointCloudStats;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [activeClasses, setActiveClasses] = useState<Record<number, boolean>>({
    64: true,
    65: true,
    66: true,
    68: true,
    6: true,
    2: false,
  });
  const [autoRotate, setAutoRotate] = useState(true);
  const [activeTab, setActiveTab] = useState<'both' | '3d' | 'equipment'>('both');
  const [tableQuery, setTableQuery] = useState('');
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null);

  const rotRef = useRef({ rotX: 0.28, rotY: 0.65, zoom: 19, panX: 0, panY: 20 });
  const isDraggingRef = useRef(false);
  const lastMousePos = useRef({ x: 0, y: 0 });

  useEffect(() => {
    let animId: number;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const render = () => {
      if (autoRotate && !isDraggingRef.current) {
        rotRef.current.rotY += 0.005;
      }

      const { rotX, rotY, zoom, panX, panY } = rotRef.current;
      const width = canvas.width;
      const height = canvas.height;

      // Dark technical backdrop
      ctx.fillStyle = '#0F172A';
      ctx.fillRect(0, 0, width, height);

      const cosY = Math.cos(rotY);
      const sinY = Math.sin(rotY);
      const cosX = Math.cos(rotX);
      const sinX = Math.sin(rotX);

      // Project 3D coordinate [x, y, z] to screen space (Z is elevation)
      const project = (x: number, y: number, z: number) => {
        const x1 = x * cosY - y * sinY;
        const y1 = x * sinY + y * cosY;
        const y2 = y1 * cosX - z * sinX;
        const z2 = y1 * sinX + z * cosX;
        const depth = Math.max(10, 400 + y2 * 3.5);
        const fov = 400 / depth;
        const scale = zoom * fov;
        const sx = width / 2 + x1 * scale + panX;
        const sy = height / 2 - z2 * scale + panY;
        return { sx, sy, depth: y2 };
      };

      // Draw coordinate compass at bottom-left
      const cx = 50;
      const cy = height - 45;
      const axisLen = 22;
      const axes = [
        { label: 'E', color: '#EF4444', x: 1, y: 0, z: 0 },
        { label: 'N', color: '#10B981', x: 0, y: 1, z: 0 },
        { label: 'UP', color: '#38BDF8', x: 0, y: 0, z: 1 },
      ];
      ctx.lineWidth = 1.8;
      axes.forEach((axis) => {
        const x1 = axis.x * cosY - axis.y * sinY;
        const y1 = axis.x * sinY + axis.y * cosY;
        const z2 = y1 * sinX + axis.z * cosX;
        ctx.strokeStyle = axis.color;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + x1 * axisLen, cy - z2 * axisLen);
        ctx.stroke();
        ctx.fillStyle = axis.color;
        ctx.font = 'bold 9px monospace';
        ctx.fillText(axis.label, cx + x1 * (axisLen + 7) - 3, cy - z2 * (axisLen + 7) + 3);
      });

      // Filter and project 3D LiDAR points
      const rendered: { sx: number; sy: number; depth: number; color: string; radius: number }[] = [];
      for (let i = 0; i < points.length; i++) {
        const pt = points[i];
        const c = pt[3];
        if (!activeClasses[c]) continue;
        const conf = CLASS_CONFIG[c] || { color: '#94A3B8', radius: 1.5 };
        const p = project(pt[0], pt[1], pt[2]);
        if (p.sx >= -20 && p.sx <= width + 20 && p.sy >= -20 && p.sy <= height + 20) {
          rendered.push({
            sx: p.sx,
            sy: p.sy,
            depth: p.depth,
            color: conf.color,
            radius: conf.radius,
          });
        }
      }

      // Sort back-to-front
      rendered.sort((a, b) => b.depth - a.depth);

      for (let i = 0; i < rendered.length; i++) {
        const p = rendered[i];
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, p.radius, 0, Math.PI * 2);
        ctx.fill();
      }

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animId);
  }, [points, activeClasses, autoRotate]);

  const filteredObjects = useMemo(() => {
    if (!objects) return [];
    const q = tableQuery.trim().toLowerCase();
    if (!q) return objects;
    return objects.filter(
      (o) =>
        o.object_id.toLowerCase().includes(q) ||
        o.object_type.toLowerCase().includes(q) ||
        (o.sector && o.sector.toLowerCase().includes(q))
    );
  }, [objects, tableQuery]);

  const totalPoints = stats?.total_points || points.length;
  const renderedPoints = stats?.rendered_points || points.length;

  return (
    <View style={{ flex: 1, gap: space(3) }}>
      {/* Top Controls & Metrics Bar */}
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: space(2),
          backgroundColor: '#F8FAFC',
          padding: space(3),
          borderRadius: 10,
          borderWidth: 1,
          borderColor: '#E2E8F0',
        }}
      >
        <Row style={{ gap: space(2), flexWrap: 'wrap', alignItems: 'center' }}>
          <Badge text={`${totalPoints.toLocaleString()} Total LiDAR Points`} color="#1E3A8A" />
          <Badge text={`${renderedPoints.toLocaleString()} Rendered in 3D`} color={colors.accent} />
          <Badge text={`${objects.length} Equipment Objects Detected`} color="#10B981" />
        </Row>

        <Row style={{ gap: space(2), alignItems: 'center' }}>
          {/* View switcher tabs */}
          <View style={{ flexDirection: 'row', backgroundColor: '#E2E8F0', borderRadius: 8, padding: 2 }}>
            {(['both', '3d', 'equipment'] as const).map((tab) => {
              const active = activeTab === tab;
              const label = tab === 'both' ? 'Split View' : tab === '3d' ? '3D Model' : 'Equipment List';
              return (
                <Pressable
                  key={tab}
                  onPress={() => setActiveTab(tab)}
                  style={{
                    paddingHorizontal: 10,
                    paddingVertical: 5,
                    borderRadius: 6,
                    backgroundColor: active ? '#1E3A8A' : 'transparent',
                  }}
                >
                  <Text style={{ fontSize: 11.5, fontWeight: '700', color: active ? '#fff' : colors.text }}>
                    {label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </Row>
      </View>

      {/* Main View Area */}
      <View style={{ flex: 1, flexDirection: activeTab === 'both' && Platform.OS === 'web' ? 'row' : 'column', gap: space(3), minHeight: 450 }}>
        {/* 3D Canvas Box */}
        {activeTab !== 'equipment' ? (
          <View
            style={{
              flex: activeTab === 'both' ? 1.2 : 1,
              borderRadius: 10,
              overflow: 'hidden',
              backgroundColor: '#0F172A',
              borderWidth: 1,
              borderColor: '#334155',
              position: 'relative',
              minHeight: 420,
            }}
          >
            {Platform.OS === 'web' ? (
              <canvas
                ref={canvasRef as any}
                width={700}
                height={460}
                style={{ width: '100%', height: '100%', display: 'block', cursor: 'grab' }}
                onMouseDown={(e: any) => {
                  isDraggingRef.current = true;
                  lastMousePos.current = { x: e.clientX, y: e.clientY };
                }}
                onMouseMove={(e: any) => {
                  if (!isDraggingRef.current) return;
                  const dx = e.clientX - lastMousePos.current.x;
                  const dy = e.clientY - lastMousePos.current.y;
                  rotRef.current.rotY += dx * 0.007;
                  rotRef.current.rotX = Math.max(-1.4, Math.min(1.4, rotRef.current.rotX + dy * 0.007));
                  lastMousePos.current = { x: e.clientX, y: e.clientY };
                }}
                onMouseUp={() => {
                  isDraggingRef.current = false;
                }}
                onMouseLeave={() => {
                  isDraggingRef.current = false;
                }}
                onWheel={(e: any) => {
                  e.preventDefault();
                  rotRef.current.zoom = Math.max(6, Math.min(65, rotRef.current.zoom - e.deltaY * 0.025));
                }}
              />
            ) : (
              <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: space(4) }}>
                <Icon name="box" size={48} color="#38BDF8" />
                <Text style={{ color: '#fff', fontWeight: '700', marginTop: 10 }}>Interactive 3D Point Cloud</Text>
              </View>
            )}

            {/* Canvas Floating Top Controls */}
            <View
              style={{
                position: 'absolute',
                top: 10,
                right: 10,
                flexDirection: 'row',
                gap: 6,
                backgroundColor: 'rgba(15, 23, 42, 0.85)',
                padding: 4,
                borderRadius: 8,
                borderWidth: 1,
                borderColor: 'rgba(255,255,255,0.12)',
              }}
            >
              <Pressable
                onPress={() => setAutoRotate(!autoRotate)}
                style={{
                  paddingHorizontal: 8,
                  paddingVertical: 4,
                  borderRadius: 6,
                  backgroundColor: autoRotate ? '#1E3A8A' : 'rgba(255,255,255,0.08)',
                }}
              >
                <Text style={{ fontSize: 11, color: '#fff', fontWeight: '700' }}>
                  {autoRotate ? '⏸ Pause Orbit' : '▶ Auto Orbit'}
                </Text>
              </Pressable>
              <Pressable
                onPress={() => {
                  rotRef.current = { rotX: 0.28, rotY: 0.65, zoom: 19, panX: 0, panY: 20 };
                }}
                style={{
                  paddingHorizontal: 8,
                  paddingVertical: 4,
                  borderRadius: 6,
                  backgroundColor: 'rgba(255,255,255,0.08)',
                }}
              >
                <Text style={{ fontSize: 11, color: '#fff', fontWeight: '700' }}>Reset View</Text>
              </Pressable>
            </View>

            {/* Canvas Bottom Legend / Class Toggles */}
            <View
              style={{
                position: 'absolute',
                bottom: 8,
                left: 10,
                right: 10,
                flexDirection: 'row',
                flexWrap: 'wrap',
                gap: 6,
                backgroundColor: 'rgba(15, 23, 42, 0.88)',
                paddingHorizontal: 10,
                paddingVertical: 6,
                borderRadius: 8,
                borderWidth: 1,
                borderColor: 'rgba(255,255,255,0.1)',
                alignItems: 'center',
              }}
            >
              <Text style={{ fontSize: 10, color: 'rgba(255,255,255,0.6)', fontWeight: '700', marginRight: 4 }}>
                LAYERS:
              </Text>
              {Object.entries(CLASS_CONFIG).map(([cKey, conf]) => {
                const cId = Number(cKey);
                const isVisible = activeClasses[cId];
                return (
                  <Pressable
                    key={cKey}
                    onPress={() => setActiveClasses((prev) => ({ ...prev, [cId]: !prev[cId] }))}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 5,
                      paddingHorizontal: 7,
                      paddingVertical: 3,
                      borderRadius: 4,
                      backgroundColor: isVisible ? 'rgba(255,255,255,0.12)' : 'transparent',
                      opacity: isVisible ? 1 : 0.45,
                    }}
                  >
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: conf.color }} />
                    <Text style={{ fontSize: 10.5, color: '#fff', fontWeight: '600' }}>{conf.label}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        ) : null}

        {/* Extracted Equipment Table Box */}
        {activeTab !== '3d' ? (
          <View
            style={{
              flex: 1,
              backgroundColor: '#fff',
              borderRadius: 10,
              borderWidth: 1,
              borderColor: '#CBD5E1',
              overflow: 'hidden',
              flexDirection: 'column',
              maxHeight: 520,
            }}
          >
            {/* Table Header & Search */}
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                paddingHorizontal: space(3),
                paddingVertical: space(2.5),
                borderBottomWidth: 1,
                borderBottomColor: '#E2E8F0',
                backgroundColor: '#F8FAFC',
                gap: space(2),
              }}
            >
              <Row style={{ alignItems: 'center', gap: 6 }}>
                <Icon name="box" size={15} color={colors.accent} />
                <Text style={{ fontSize: 13, fontWeight: '800', color: colors.text }}>
                  Extracted Physical Equipment ({filteredObjects.length})
                </Text>
              </Row>
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  backgroundColor: '#fff',
                  borderWidth: 1,
                  borderColor: '#CBD5E1',
                  borderRadius: 6,
                  paddingHorizontal: 8,
                  paddingVertical: 4,
                  width: 170,
                }}
              >
                <Icon name="search" size={12} color={colors.muted} />
                <TextInput
                  value={tableQuery}
                  onChangeText={setTableQuery}
                  placeholder="Filter objects..."
                  placeholderTextColor={colors.muted}
                  style={{ flex: 1, fontSize: 11, marginLeft: 5, outlineStyle: 'none' as any }}
                />
              </View>
            </View>

            {/* Table Content */}
            <ScrollView horizontal showsHorizontalScrollIndicator>
              <View style={{ minWidth: 620 }}>
                {/* Column Headers */}
                <View style={{ flexDirection: 'row', backgroundColor: '#1E3A8A', paddingVertical: 7, paddingHorizontal: 8 }}>
                  <Text style={{ width: 75, color: '#fff', fontSize: 11, fontWeight: '700' }}>Object ID</Text>
                  <Text style={{ width: 110, color: '#fff', fontSize: 11, fontWeight: '700' }}>Equipment Type</Text>
                  <Text style={{ width: 70, color: '#fff', fontSize: 11, fontWeight: '700' }}>Facing</Text>
                  <Text style={{ width: 85, color: '#fff', fontSize: 11, fontWeight: '700' }}>Elevation</Text>
                  <Text style={{ width: 140, color: '#fff', fontSize: 11, fontWeight: '700' }}>Dimensions (H×W×D)</Text>
                  <Text style={{ width: 85, color: '#fff', fontSize: 11, fontWeight: '700' }}>Confidence</Text>
                </View>

                {/* Rows */}
                <ScrollView style={{ maxHeight: 420 }} nestedScrollEnabled>
                  {filteredObjects.length === 0 ? (
                    <View style={{ padding: space(5), alignItems: 'center' }}>
                      <Muted>No matching equipment objects found.</Muted>
                    </View>
                  ) : (
                    filteredObjects.map((obj, idx) => {
                      const isAntenna = obj.object_type === 'Antenna';
                      const isRRU = obj.object_type === 'Remote radio';
                      const isMount = obj.object_type === 'Mount pipe';
                      const isSelected = selectedObjectId === obj.object_id;

                      const badgeBg = isAntenna ? '#EFF6FF' : isRRU ? '#FAF5FF' : isMount ? '#FFFBEB' : '#F1F5F9';
                      const badgeColor = isAntenna ? '#1D4ED8' : isRRU ? '#7E22CE' : isMount ? '#B45309' : colors.text;

                      return (
                        <Pressable
                          key={obj.object_id || idx}
                          onPress={() => setSelectedObjectId(isSelected ? null : obj.object_id)}
                          style={{
                            flexDirection: 'row',
                            alignItems: 'center',
                            paddingVertical: 7,
                            paddingHorizontal: 8,
                            backgroundColor: isSelected ? '#EFF6FF' : idx % 2 === 1 ? '#F8FAFC' : '#fff',
                            borderBottomWidth: 1,
                            borderBottomColor: '#E2E8F0',
                          }}
                        >
                          <Text style={{ width: 75, fontSize: 11.5, fontWeight: '700', color: colors.text }}>
                            {obj.object_id}
                          </Text>
                          <View style={{ width: 110 }}>
                            <View style={{ alignSelf: 'flex-start', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: badgeBg }}>
                              <Text style={{ fontSize: 10.5, fontWeight: '700', color: badgeColor }}>
                                {obj.object_type}
                              </Text>
                            </View>
                          </View>
                          <Text style={{ width: 70, fontSize: 11.5, color: colors.text }}>
                            {obj.facing_az_deg !== null && obj.facing_az_deg !== undefined ? `${obj.facing_az_deg}°` : '—'}
                          </Text>
                          <Text style={{ width: 85, fontSize: 11.5, color: colors.text }}>
                            {obj.center_height_ft !== null && obj.center_height_ft !== undefined ? `${obj.center_height_ft} ft` : '—'}
                          </Text>
                          <Text style={{ width: 140, fontSize: 11, color: colors.text, fontFamily: 'monospace' }}>
                            {obj.dimensions_in && obj.dimensions_in.length >= 3
                              ? `${obj.dimensions_in[0]}" × ${obj.dimensions_in[1]}" × ${obj.dimensions_in[2]}"`
                              : '—'}
                          </Text>
                          <View style={{ width: 85, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                            <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: (obj.confidence || 0) >= 90 ? '#10B981' : '#F59E0B' }} />
                            <Text style={{ fontSize: 11, fontWeight: '700', color: colors.text }}>
                              {obj.confidence ? `${obj.confidence}%` : '—'}
                            </Text>
                          </View>
                        </Pressable>
                      );
                    })
                  )}
                </ScrollView>
              </View>
            </ScrollView>
          </View>
        ) : null}
      </View>
    </View>
  );
}

function PdfViewer({
  pages = [],
  fileUrl,
  fileName,
}: {
  pages?: PdfPage[];
  fileUrl?: string;
  fileName: string;
}) {
  const [currentPage, setCurrentPage] = useState(1);
  const [zoomLevel, setZoomLevel] = useState<'fit' | '100%' | '150%' | '200%'>('fit');

  const page = pages.find((p) => p.page_number === currentPage) || pages[0];

  if (!pages || pages.length === 0) {
    if (Platform.OS === 'web' && fileUrl) {
      return (
        <View style={{ flex: 1, minHeight: 650, borderRadius: 8, overflow: 'hidden', borderWidth: 1, borderColor: colors.border, backgroundColor: '#525659' }}>
          {React.createElement('iframe', {
            src: `${fileUrl}#view=FitH&toolbar=1`,
            title: fileName,
            style: { width: '100%', height: '100%', minHeight: 650, border: 'none', backgroundColor: '#525659' },
          })}
        </View>
      );
    }
    return (
      <View style={styles.centered}>
        <Icon name="file-text" size={48} color={colors.accent} />
        <Text style={{ marginTop: space(2), fontSize: 15, fontWeight: '700', color: colors.text }}>
          PDF Document
        </Text>
        <Text style={{ marginTop: 4, color: colors.muted, textAlign: 'center' }}>
          Open PDF in your browser or document viewer.
        </Text>
        {fileUrl ? (
          <View style={{ marginTop: space(4) }}>
            <Button title="Open PDF" onPress={() => Linking.openURL(fileUrl)} />
          </View>
        ) : null}
      </View>
    );
  }

  const zoomScale = zoomLevel === 'fit' ? 1 : zoomLevel === '100%' ? 1 : zoomLevel === '150%' ? 1.5 : 2;

  return (
    <View style={{ flex: 1, gap: space(3) }}>
      {/* Controls Bar */}
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: space(2),
          backgroundColor: '#F8FAFC',
          padding: space(2.5),
          borderRadius: 10,
          borderWidth: 1,
          borderColor: '#E2E8F0',
        }}
      >
        {/* Sheet navigation */}
        <Row style={{ alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
          <Button
            small
            kind="secondary"
            title="◀ Prev"
            disabled={currentPage <= 1}
            onPress={() => setCurrentPage((p) => Math.max(1, p - 1))}
          />
          <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }}>
            Sheet {currentPage} of {pages.length}
          </Text>
          <Button
            small
            kind="secondary"
            title="Next ▶"
            disabled={currentPage >= pages.length}
            onPress={() => setCurrentPage((p) => Math.min(pages.length, p + 1))}
          />

          {/* Quick sheet pill tabs */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 4, marginLeft: 8 }}>
            {pages.map((p) => {
              const active = p.page_number === currentPage;
              return (
                <Pressable
                  key={p.page_number}
                  onPress={() => setCurrentPage(p.page_number)}
                  style={{
                    paddingHorizontal: 10,
                    paddingVertical: 5,
                    borderRadius: 6,
                    backgroundColor: active ? '#1E3A8A' : '#E2E8F0',
                  }}
                >
                  <Text style={{ fontSize: 11.5, fontWeight: '700', color: active ? '#fff' : colors.text }}>
                    Sheet {p.page_number}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
        </Row>

        {/* Zoom controls */}
        <Row style={{ alignItems: 'center', gap: space(1.5) }}>
          <Text style={{ fontSize: 12, color: colors.muted, fontWeight: '600', marginRight: 4 }}>Zoom:</Text>
          {(['fit', '100%', '150%', '200%'] as const).map((z) => {
            const active = zoomLevel === z;
            return (
              <Pressable
                key={z}
                onPress={() => setZoomLevel(z)}
                style={{
                  paddingHorizontal: 9,
                  paddingVertical: 4,
                  borderRadius: 6,
                  backgroundColor: active ? '#1E3A8A' : '#E2E8F0',
                }}
              >
                <Text style={{ fontSize: 11.5, fontWeight: '700', color: active ? '#fff' : colors.text }}>
                  {z === 'fit' ? 'Fit Width' : z}
                </Text>
              </Pressable>
            );
          })}
        </Row>
      </View>

      {/* Sheet Image Container */}
      <ScrollView
        horizontal={zoomLevel !== 'fit'}
        contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', alignItems: 'center' }}
        style={{
          flex: 1,
          backgroundColor: '#1E293B',
          borderRadius: 10,
          overflow: 'hidden',
          minHeight: 520,
        }}
      >
        <ScrollView
          nestedScrollEnabled
          contentContainerStyle={{ padding: space(3), alignItems: 'center', justifyContent: 'center', minWidth: '100%' }}
        >
          {page && Platform.OS === 'web' ? (
            React.createElement('img', {
              src: page.image,
              alt: `Sheet ${currentPage} - ${fileName}`,
              style: {
                width: zoomLevel === 'fit' ? '100%' : `${zoomScale * 100}%`,
                maxWidth: zoomLevel === 'fit' ? '100%' : undefined,
                height: 'auto',
                boxShadow: '0 8px 30px rgba(0,0,0,0.4)',
                borderRadius: 4,
                display: 'block',
              },
            })
          ) : null}
        </ScrollView>
      </ScrollView>
    </View>
  );
}

export function FilePreviewModal({
  target,
  onClose,
}: {
  target: FilePreviewTarget | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!target) {
      setData(null);
      setError(null);
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);

    const url = target.docId
      ? `/documents/${target.docId}/preview`
      : `/sharepoint/sites/${target.siteId}/files/preview?folder=${encodeURIComponent(target.folder || '')}&file_name=${encodeURIComponent(target.name)}`;

    api
      .get<PreviewData>(url)
      .then((res) => {
        if (isMounted) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err: any) => {
        if (isMounted) {
          setError(err?.message || 'Could not load file preview');
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [target]);

  if (!target) return null;

  const downloadUrl = data?.download_url
    ? authedUrl(data.download_url + (data.download_url.includes('?') ? '&' : '?') + 'disposition=attachment')
    : target.docId
    ? authedUrl(`/documents/${target.docId}/download?disposition=attachment`)
    : target.siteId && target.folder
    ? authedUrl(`/sharepoint/sites/${target.siteId}/files/download?folder=${encodeURIComponent(target.folder)}&file_name=${encodeURIComponent(target.name)}&disposition=attachment`)
    : null;

  const inlineUrl = data?.file_url
    ? authedUrl(data.file_url)
    : data?.download_url
    ? authedUrl(data.download_url + (data.download_url.includes('?') ? '&' : '?') + 'disposition=inline')
    : downloadUrl;

  return (
    <Modal visible={Boolean(target)} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.container}>
          {/* Header */}
          <View style={styles.header}>
            <Row style={{ alignItems: 'center', gap: space(3), flex: 1 }}>
              <IconBadge name={fileIcon(target.name)} size={42} color={colors.accent} />
              <View style={{ flex: 1 }}>
                <Row style={{ alignItems: 'center', gap: space(2), flexWrap: 'wrap' }}>
                  <Text style={{ fontSize: 16, fontWeight: '800', color: colors.text }} numberOfLines={1}>
                    {target.name}
                  </Text>
                  {data?.doc_type ? <Badge text={data.doc_type} color={colors.accent} /> : null}
                  {data?.format ? <Badge text={data.format} color={colors.muted} /> : null}
                </Row>
                <Muted style={{ fontSize: 12, marginTop: 2 }}>
                  {[kb(data?.size || target.size), data?.modified ? `Updated ${data.modified.split('T')[0]}` : null, target.folder ? `Folder: ${target.folder}` : null]
                    .filter(Boolean)
                    .join(' · ')}
                </Muted>
              </View>
            </Row>

            <Row style={{ alignItems: 'center', gap: space(2) }}>
              {downloadUrl ? (
                <Button
                  small
                  title="Download"
                  onPress={() => Linking.openURL(downloadUrl)}
                />
              ) : null}
              {inlineUrl && (data?.type === 'pdf' || data?.type === 'image' || data?.type === 'video') ? (
                <Button
                  small
                  kind="secondary"
                  title="New Tab"
                  onPress={() => Linking.openURL(inlineUrl)}
                />
              ) : null}
              <Pressable
                onPress={onClose}
                style={({ pressed }) => [styles.closeButton, pressed && { backgroundColor: '#E2E8F0' }]}
                accessibilityLabel="Close"
              >
                <Icon name="x" size={18} color={colors.text} />
              </Pressable>
            </Row>
          </View>

          {/* Body Content */}
          <View style={styles.body}>
            {loading ? (
              <View style={styles.centered}>
                <ActivityIndicator size="large" color={colors.accent} />
                <Text style={{ marginTop: space(3), color: colors.muted, fontWeight: '600' }}>
                  Loading file preview...
                </Text>
              </View>
            ) : error ? (
              <View style={styles.centered}>
                <Icon name="alert-triangle" size={36} color={colors.danger} />
                <Text style={{ marginTop: space(2), fontSize: 15, fontWeight: '700', color: colors.danger }}>
                  Preview Error
                </Text>
                <Text style={{ marginTop: space(1), color: colors.muted, textAlign: 'center' }}>
                  {error}
                </Text>
                {downloadUrl ? (
                  <View style={{ marginTop: space(4) }}>
                    <Button title="Download File Instead" onPress={() => Linking.openURL(downloadUrl)} />
                  </View>
                ) : null}
              </View>
            ) : !data ? null : data.type === 'spreadsheet' && data.sheets ? (
              <SpreadsheetViewer sheets={data.sheets} />
            ) : data.type === 'pointcloud' && data.points && data.points.length > 0 ? (
              <PointCloudViewer points={data.points} objects={data.objects} stats={data.stats} />
            ) : data.type === 'pdf' ? (
              <PdfViewer pages={data.pages} fileUrl={inlineUrl || undefined} fileName={data.file_name} />
            ) : data.type === 'image' && inlineUrl ? (
              <ScrollView contentContainerStyle={{ alignItems: 'center', padding: space(4) }}>
                {Platform.OS === 'web' ? (
                  React.createElement('img', {
                    src: inlineUrl,
                    alt: data.file_name,
                    style: { maxWidth: '100%', maxHeight: 600, objectFit: 'contain', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.1)' },
                  })
                ) : (
                  <View style={styles.centered}>
                    <Button title="View Full Image" onPress={() => inlineUrl && Linking.openURL(inlineUrl)} />
                  </View>
                )}
              </ScrollView>
            ) : data.type === 'video' && inlineUrl ? (
              <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: space(3) }}>
                {Platform.OS === 'web' ? (
                  React.createElement('video', {
                    src: inlineUrl,
                    controls: true,
                    autoPlay: false,
                    style: { width: '100%', maxHeight: 540, borderRadius: 10, backgroundColor: '#000' },
                  })
                ) : (
                  <View style={styles.centered}>
                    <Icon name="video" size={48} color={colors.accent} />
                    <Button title="Play Video in Browser" onPress={() => inlineUrl && Linking.openURL(inlineUrl)} />
                  </View>
                )}
              </View>
            ) : data.type === 'json' || data.type === 'text' ? (
              <View style={{ flex: 1, backgroundColor: '#0F172A', borderRadius: 10, padding: space(4), maxHeight: 580 }}>
                <ScrollView horizontal showsHorizontalScrollIndicator>
                  <ScrollView nestedScrollEnabled showsVerticalScrollIndicator>
                    <Text style={{ fontFamily: 'monospace', fontSize: 12, color: '#E2E8F0', lineHeight: 18 }}>
                      {data.type === 'json' ? JSON.stringify(data.content, null, 2) : data.content}
                    </Text>
                  </ScrollView>
                </ScrollView>
              </View>
            ) : (
              <View style={styles.centered}>
                <IconBadge name={fileIcon(target.name)} size={64} color={colors.accent} />
                <Text style={{ marginTop: space(3), fontSize: 16, fontWeight: '800', color: colors.text }}>
                  {data?.category || `${data?.format || 'Unknown'} File`}
                </Text>
                <Text style={{ marginTop: space(1), color: colors.muted, textAlign: 'center', maxWidth: 460 }}>
                  {data?.note || 'This file format is ready for download and offline analysis in engineering software.'}
                </Text>
                {downloadUrl ? (
                  <View style={{ marginTop: space(4) }}>
                    <Button title={`Download ${data?.file_name || target.name}`} onPress={() => Linking.openURL(downloadUrl)} />
                  </View>
                ) : null}
              </View>
            )}
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.72)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: space(4),
  },
  container: {
    width: '100%',
    maxWidth: 1240,
    maxHeight: '94%',
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    overflow: 'hidden',
    ...shadow,
    flexDirection: 'column',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space(5),
    paddingVertical: space(3.5),
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: '#F8FAFC',
    gap: space(3),
  },
  closeButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#F1F5F9',
  },
  body: {
    flex: 1,
    padding: space(5),
    minHeight: 450,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space(6),
  },
});
