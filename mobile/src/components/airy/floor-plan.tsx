import { Image } from 'expo-image';
import { StyleSheet, View } from 'react-native';
import { useState } from 'react';

import { Card, colors, Copy, layout } from './ui';
import { roomName, type HouseMap, type SimulatorState } from '@/lib/simulation';

const purifierHalo = require('@/assets/airy/AirPurifierHalo.svg');
const purifierIcon = require('@/assets/airy/AirPurifierPosition.svg');
const destinationRing = require('@/assets/airy/Destination.svg');
const destinationCenter = require('@/assets/airy/DestinationCenter.svg');

export function FloorPlan({ map, state }: { map: HouseMap; state: SimulatorState }) {
  const [width, setWidth] = useState(0);
  const height = width * 210 / 317;
  // The server grid includes a one-cell perimeter. The room outlines represent those exterior walls.
  const cellWidth = width / Math.max(1, map.width - 2);
  const cellHeight = height / Math.max(1, map.height - 2);
  const point = ([x, y]: number[]) => ({ left: (x - 0.5) * cellWidth, top: (y - 0.5) * cellHeight });
  const returning = state.device_state === 'returning';
  const target = state.remaining_steps === 0 ? undefined
    : returning ? state.dock : map.rooms.find(room => room.id === state.destination)?.target;
  const path = state.is_running && (state.mode === 'auto' || returning) ? [state.position, ...(state.remaining_path ?? [])] : [];
  const dock = map.dock ?? state.dock;
  const tiles = map.grid.flatMap((row, y) => Array.from(row, (tile, x) => ({ tile, x, y })));
  const tileAt = (x: number, y: number) => map.grid[y]?.[x];

  return (
    <Card>
      <View style={layout.row}>
        <Copy size={16} bold>Floor Plan</Copy>
        <Copy size={10} color={colors.muted}>{state.is_running ? 'Live position' : 'Position paused'}</Copy>
      </View>
      <View onLayout={event => setWidth(event.nativeEvent.layout.width)} style={styles.plan}>
        {width > 0 && <>
          {map.rooms.map(room => {
            const [x1, y1, x2, y2] = room.bounds;
            // Extend room outlines into half of the adjacent interior wall.
            const insetLeft = x1 === 1 ? 0 : 4;
            const insetTop = y1 === 1 ? 0 : 4;
            const insetRight = x2 === map.width - 2 ? 0 : 4;
            const insetBottom = y2 === map.height - 2 ? 0 : 4;
            const left = x1 === 1 ? 0 : point([x1 - 1, y1]).left + insetLeft;
            const top = y1 === 1 ? 0 : point([x1, y1 - 1]).top + insetTop;
            const right = x2 === map.width - 2 ? width : point([x2 + 1, y2]).left - insetRight;
            const bottom = y2 === map.height - 2 ? height : point([x2, y2 + 1]).top - insetBottom;
            return <View key={room.id} style={[styles.room, { left, top, width: right - left, height: bottom - top }]}>
              <Copy size={11} color={colors.red} bold>{roomName(room.id, room.name)}</Copy>
            </View>;
          })}
          {tiles.map(({ tile, x, y }) => {
            const { left, top } = point([x, y]);
            if (tile === 'D') {
              const horizontal = tileAt(x - 1, y) === '#' && tileAt(x + 1, y) === '#';
              return <View key={`door-${x}-${y}`} style={[styles.door, {
                left: left - (horizontal ? cellWidth / 2 : 4), top: top - (horizontal ? 4 : cellHeight / 2),
                width: horizontal ? cellWidth : 8, height: horizontal ? 8 : cellHeight,
              }]}><View style={[styles.arc, horizontal && styles.horizontalArc]} /></View>;
            }
            if (tile !== 'X') return null;
            const l = tileAt(x - 1, y) === 'X' ? 0 : 3;
            const r = tileAt(x + 1, y) === 'X' ? 0 : 3;
            const t = tileAt(x, y - 1) === 'X' ? 0 : 3;
            const b = tileAt(x, y + 1) === 'X' ? 0 : 3;
            return <View key={`obstacle-${x}-${y}`} style={[styles.obstacle, {
              left: left - cellWidth / 2 + l, top: top - cellHeight / 2 + t,
              width: cellWidth - l - r, height: cellHeight - t - b,
              borderTopLeftRadius: l && t ? 6 : 0, borderTopRightRadius: r && t ? 6 : 0,
              borderBottomLeftRadius: l && b ? 6 : 0, borderBottomRightRadius: r && b ? 6 : 0,
            }]} />;
          })}
          {path.slice(1).flatMap((position, index) => {
            const from = point(path[index]);
            const to = point(position);
            const length = Math.hypot(to.left - from.left, to.top - from.top);
            return Array.from({ length: Math.floor(length / 6) }, (_, dash) => {
              const fraction = (dash * 6 + 2) / length;
              return <View key={`${index}-${dash}`} style={[styles.dash, {
                left: from.left + (to.left - from.left) * fraction - 1,
                top: from.top + (to.top - from.top) * fraction - 1,
              }]} />;
            });
          })}
          {dock && <View style={[styles.dock, point(dock)]} />}
          {target && <View style={[styles.destination, point(target)]}>
            <Image source={destinationRing} style={{ width: 18, height: 18 }} />
            <Image source={destinationCenter} style={styles.destinationCenter} />
          </View>}
          <View style={[styles.purifier, point(state.position)]}>
            <Image source={purifierHalo} style={{ width: 38, height: 38 }} />
            <Image source={purifierIcon} style={styles.purifierCenter} />
          </View>
        </>}
      </View>
      <View style={layout.row}>
        <Copy size={10} bold color={colors.blue}>● Purifier</Copy>
        <Copy size={10} bold color={colors.red}>◎ Destination</Copy>
        <Copy size={10} color={colors.muted}>▬ Obstacle</Copy>
        <Copy size={10} bold color={colors.green}>■ Dock</Copy>
      </View>
      <Copy size={10} color={colors.muted}>Openings &amp; arcs indicate doors.</Copy>
    </Card>
  );
}

const styles = StyleSheet.create({
  plan: { aspectRatio: 317 / 210 },
  room: {
    position: 'absolute', backgroundColor: 'rgba(165,0,52,0.05)', borderWidth: 1,
    borderColor: 'rgba(165,0,52,0.25)', borderRadius: 14, paddingHorizontal: 10, paddingTop: 8,
  },
  door: { position: 'absolute', backgroundColor: '#e5f6fc' },
  arc: { width: 24, height: 24, borderTopWidth: 1, borderRightWidth: 1, borderColor: 'rgba(165,0,52,0.38)', borderTopRightRadius: 24 },
  horizontalArc: { transform: [{ rotate: '90deg' }] },
  obstacle: { position: 'absolute', backgroundColor: 'rgba(165,0,52,0.18)' },
  dash: { position: 'absolute', width: 2, height: 2, backgroundColor: colors.blue },
  purifier: { position: 'absolute', marginLeft: -19, marginTop: -19 },
  purifierCenter: { position: 'absolute', top: 8, left: 8, width: 22, height: 22 },
  destination: { position: 'absolute', marginLeft: -9, marginTop: -9 },
  dock: { position: 'absolute', marginLeft: -7, marginTop: -7, width: 14, height: 14, borderRadius: 3, backgroundColor: colors.green, opacity: 0.7 },
  destinationCenter: { position: 'absolute', top: 5, left: 5, width: 8, height: 8 },
});
