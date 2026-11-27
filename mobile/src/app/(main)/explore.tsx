import { Image } from 'expo-image';
import { useFocusEffect } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, StyleSheet, View } from 'react-native';

import { AiryScreen, Button, Card, colors, Copy, Header, layout } from '@/components/airy/ui';
import { formatTime, roomName, simulationRequest, type SimulatorState } from '@/lib/simulation';

type HistoryEvent = {
  time_seconds: number;
  type: string;
  room?: string;
  destination?: string;
  pm25?: number;
};

const glyphs = {
  movement: require('@/assets/airy/MovementGlyph.svg'),
  measurement: require('@/assets/airy/MeasurementGlyph.svg'),
  purification: require('@/assets/airy/PurificationGlyph.svg'),
  system: require('@/assets/airy/SystemGlyph.svg'),
};

function HistoryCard({ event, origin }: { event: HistoryEvent; origin?: string }) {
  const room = roomName(event.room, '');
  const destination = roomName(event.destination, '');
  const events: Record<string, [keyof typeof glyphs, string, string?]> = {
    move_requested: ['movement', 'Movement Requested', [origin, destination].filter(Boolean).join(' → ')],
    arrival: ['movement', 'Arrival', room],
    measurement: ['measurement', 'Air Quality Measurement', [
      room, event.pm25 == null ? undefined : `${event.pm25.toFixed(1)} µg/m³`,
    ].filter(Boolean).join(' · ')],
    purification_on: ['purification', 'Purification Started', room],
    purification_off: ['purification', 'Purification Stopped', room],
    return_requested: ['movement', 'Return to Dock'],
    docked: ['movement', 'Arrived at Dock'],
    replanned: ['movement', 'Route Replanned'],
    route_blocked: ['movement', 'Route Blocked'],
    operation_stopped: ['system', 'Device Stopped'],
    operation_started: ['system', 'Device Started'],
    start: ['system', 'Simulation Started'],
    pause: ['system', 'Simulation Paused'],
    reset: ['system', 'Simulation Reset'],
    day_finished: ['system', 'Simulation Finished'],
  };
  const [category, title, detail] = events[event.type] ?? ['system', event.type.replaceAll('_', ' ')];
  return (
    <Card style={styles.event}>
      <View style={styles.iconBubble}>
        <Image source={glyphs[category]} style={styles.glyph} />
      </View>
      <View style={styles.eventCopy}>
        <Copy size={10} color={colors.muted}>{formatTime(event.time_seconds)}</Copy>
        <Copy bold>{title}</Copy>
        {detail ? <Copy size={11} color={colors.muted}>{detail}</Copy> : null}
      </View>
    </Card>
  );
}

export default function HistoryScreen() {
  const [entries, setEntries] = useState<{ event: HistoryEvent; origin?: string }[]>([]);
  const [simulationTime, setSimulationTime] = useState<number>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const retry = useRef<(() => Promise<void>) | null>(null);

  useFocusEffect(useCallback(() => {
    let active = true;
    let inFlight = false;
    const loadHistory = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const [history, status] = await Promise.allSettled([
          simulationRequest<HistoryEvent[]>('history'),
          simulationRequest<SimulatorState>('status'),
        ]);
        if (!active) return;
        if (history.status === 'fulfilled') {
          let location: string | undefined;
          setEntries(history.value.map(event => {
            if (event.type === 'reset') location = undefined;
            if (event.room) location = roomName(event.room);
            return { event, origin: location };
          }).reverse());
        }
        if (status.status === 'fulfilled') setSimulationTime(status.value.simulation_time_seconds);
        setError(history.status === 'rejected');
      } finally {
        inFlight = false;
        if (active) setLoading(false);
      }
    };
    retry.current = loadHistory;
    void loadHistory();
    const timer = setInterval(() => { void loadHistory(); }, 5000);
    return () => {
      active = false;
      retry.current = null;
      clearInterval(timer);
    };
  }, []));

  return (
    <AiryScreen>
      <Header title="My History" subtitle="Every step toward cleaner air" />
      <FlatList
        data={entries}
        keyExtractor={({ event }, index) => `${event.time_seconds}-${event.type}-${entries.length - index}`}
        contentContainerStyle={layout.list}
        ListHeaderComponent={<View style={styles.summary}>
          <Card>
            <View style={layout.row}>
              <Copy color={colors.muted}>Simulation Time</Copy>
              <Copy size={17} color={colors.red} bold>{simulationTime == null ? '—' : formatTime(simulationTime)}</Copy>
            </View>
            <View style={layout.row}>
              <Copy size={10} color={colors.blue} bold>→ Movement</Copy>
              <Copy size={10} color={colors.purple} bold>● Measurement</Copy>
              <Copy size={10} color={colors.green} bold>≈ Purification</Copy>
            </View>
          </Card>
          <Copy size={11} color={colors.muted}>Newest first</Copy>
          {loading && <ActivityIndicator color={colors.red} accessibilityLabel="Loading history" />}
          {error && <Card>
            <Copy color={colors.red}>Unable to load the latest history.</Copy>
            <Button label="Retry" onPress={() => { setLoading(true); void retry.current?.(); }} />
          </Card>}
        </View>}
        ListEmptyComponent={!loading && !error ? <Copy color={colors.muted}>No activity recorded yet.</Copy> : undefined}
        renderItem={({ item }) => <HistoryCard {...item} />}
      />
    </AiryScreen>
  );
}

const styles = StyleSheet.create({
  summary: { gap: 14 },
  event: { flexDirection: 'row', alignItems: 'flex-start', paddingHorizontal: 16, paddingVertical: 14, minHeight: 86 },
  iconBubble: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.white },
  glyph: { width: 20, height: 20 },
  eventCopy: { flex: 1, gap: 2 },
});
