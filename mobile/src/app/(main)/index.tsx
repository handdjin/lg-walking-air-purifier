import { Image } from 'expo-image';
import { useFocusEffect } from 'expo-router';
import { useCallback, useContext, useRef, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';

import { FloorPlan } from '@/components/airy/floor-plan';
import { AiryScreen, Button, Card, colors, Copy, Header, layout } from '@/components/airy/ui';
import { AuthStateContext, clearSession } from '@/lib/auth-session';
import { formatTime, roomName, simulationRequest, type HouseMap, type Room, type SimulatorState } from '@/lib/simulation';

const reasons: Record<string, string> = {
  all_predictions_below_threshold: 'All room forecasts are below the threshold.',
  no_reachable_candidate: 'No reachable destination is available.',
  current_room_selected: 'Airy is staying in the current room.',
  highest_score: 'Airy selected this room based on predicted pollution and travel time.',
};

type Connection = 'loading' | 'online' | 'offline';

function ConnectionCard({ loading, reconnect }: { loading: boolean; reconnect: () => void }) {
  return (
    <View style={styles.system}>
      <Card style={styles.systemCard}>
        <View style={styles.systemIcon}>
          <Image source={loading ? require('@/assets/airy/LoadingGlyph.svg') : require('@/assets/airy/ConnectionFailedGlyph.svg')} style={styles.systemGlyph} />
        </View>
        <Copy size={22} bold color={colors.red}>{loading ? 'Loading...' : 'Connection Failed'}</Copy>
        <Copy size={12} color={colors.muted} style={styles.centerText}>
          {loading ? 'Connecting to your air purifier.' : 'Unable to connect to your air purifier.'}
        </Copy>
        <Button style={styles.fullWidth} label={loading ? 'Loading...' : 'Reconnect'} disabled={loading} onPress={reconnect} />
      </Card>
      <Copy size={12} color={colors.muted} style={styles.centerText}>
        {loading ? 'Device status will appear once connected.' : 'Reconnect to load the latest simulation state.'}
      </Copy>
    </View>
  );
}

function DeviceStatus({ state }: { state: SimulatorState }) {
  const status = state.finished ? 'Finished'
    : !state.is_running ? 'Paused'
    : state.status === 'moving' ? 'Moving'
    : state.is_measuring ? 'Measuring'
    : state.is_purifying ? 'Purifying' : 'Idle';
  const tint = { Finished: colors.muted, Paused: colors.gold, Moving: colors.blue, Measuring: colors.purple, Purifying: colors.green, Idle: colors.muted }[status];
  const dot = status === 'Moving' ? require('@/assets/airy/StatusDotHome.svg')
    : status === 'Paused' ? require('@/assets/airy/StatusDotManual.svg') : undefined;
  return <Card>
    <View style={layout.row}>
      <Copy size={16} bold>Device Status</Copy>
      <View style={styles.badge}>
        {dot ? <Image source={dot} style={styles.dot} /> : <View style={[styles.dot, { backgroundColor: tint }]} />}
        <Copy size={11} color={tint} bold>{status}</Copy>
      </View>
    </View>
    <View style={layout.columns}>
      <View style={layout.column}>
        <Copy size={10} color={colors.muted}>Current Location</Copy>
        <Copy size={14} bold>{roomName(state.current_room)}</Copy>
      </View>
      <View style={layout.column}>
        <Copy size={10} color={colors.muted}>Simulation Time</Copy>
        <Copy size={14} bold>{formatTime(state.simulation_time_seconds)}</Copy>
      </View>
    </View>
  </Card>;
}

function AirQuality({ room, state }: { room: Room; state: SimulatorState }) {
  const observation = state.observations[room.id];
  const measurement = observation?.pm25;
  const prediction = state.ai_prediction?.status === 'ok' ? state.ai_prediction.predictions[room.id] : null;
  const age = observation?.age_seconds;
  return <Card>
    <Copy size={16} bold>{roomName(room.id, room.name)}</Copy>
    <View style={layout.columns}>
      <View style={layout.column}>
        <Copy size={10} color={colors.muted}>Last Measured PM2.5</Copy>
        <Copy size={measurement == null ? 13 : 20} color={measurement == null ? colors.muted : colors.ink} bold>
          {measurement == null ? 'Not Measured' : `${measurement.toFixed(1)} µg/m³`}
        </Copy>
      </View>
      <View style={layout.column}>
        <Copy size={10} color={colors.muted}>30-min AI Forecast</Copy>
        <Copy size={20} color={colors.red} bold>{prediction == null ? '—' : `${prediction.toFixed(1)} µg/m³`}</Copy>
      </View>
    </View>
    <Copy size={10} color={measurement == null ? colors.gold : colors.muted}>
      {measurement == null ? 'Initial Measurement Required' : age == null ? 'Measurement age unavailable' :
        `Time since last measurement · ${age >= 60 ? `${Math.floor(age / 60)} min ` : ''}${age % 60} sec`}
    </Copy>
  </Card>;
}

type Command = (endpoint: string, body?: object) => void;

function Operations({ map, state, busy, command }: { map: HouseMap; state: SimulatorState; busy: boolean; command: Command }) {
  const manual = state.mode === 'manual';
  const pending = state.mode !== state.active_mode;
  return <Card>
    <Copy size={16} bold>Operation Mode</Copy>
    <View style={styles.modeSelector}>
      {(['auto', 'manual'] as const).map(mode => (
        <Button key={mode} compact label={mode === 'auto' ? 'Auto Mode' : 'Manual Mode'}
          selected={state.mode === mode} variant={state.mode === mode ? 'primary' : 'secondary'}
          disabled={state.mode !== mode && (busy || state.finished)} onPress={() => {
            if (state.mode !== mode) command('mode', { mode });
          }} />
      ))}
    </View>
    <Copy size={11} color={pending ? colors.gold : colors.muted}>
      {pending ? 'Mode switches after Airy reaches its current destination.'
        : manual ? 'Choose where Airy should go next.' : 'AI selects the destination automatically.'}
    </Copy>
    <Copy bold>Destination Selection</Copy>
    <View style={layout.columns}>
      {map.rooms.map(room => <Button key={room.id} compact label={roomName(room.id, room.name)}
        selected={manual && state.destination === room.id}
        variant={manual && state.destination === room.id ? 'primary' : 'secondary'}
        disabled={busy || state.finished || !manual || pending}
        onPress={() => command('move', { target_room: room.id })} />)}
    </View>
    <Copy size={11} color={colors.muted}>
      {pending ? 'Waiting for the current route to finish.'
        : !manual ? 'Destination selection is disabled in Auto Mode.'
        : state.destination ? `Selected Destination · ${roomName(state.destination)}` : 'No destination selected.'}
    </Copy>
    <Copy bold>Simulation Controls</Copy>
    <View style={layout.columns}>
      <Button compact label="Start" disabled={busy || state.is_running || state.finished} onPress={() => command('start')} />
      <Button compact label="Pause" disabled={busy || !state.is_running} onPress={() => command('pause')} />
      <Button compact label="Reset" variant="secondary" disabled={busy} onPress={() => command('reset')} />
    </View>
  </Card>;
}

export default function HomeScreen() {
  const setSignedIn = useContext(AuthStateContext);
  const signOutInProgress = useRef(false);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState(false);
  const [map, setMap] = useState<HouseMap>();
  const [state, setState] = useState<SimulatorState>();
  const [connection, setConnection] = useState<Connection>('loading');
  const [commandError, setCommandError] = useState('');
  const [busy, setBusy] = useState(false);
  const polling = useRef<Promise<void> | null>(null);
  const commanding = useRef(false);
  const loadedMap = useRef<HouseMap | undefined>(undefined);

  const refresh = useCallback((reconnect = false) => {
    if (polling.current) return polling.current;
    if (reconnect) setConnection('loading');

    const request = Promise.all([
      simulationRequest<SimulatorState>('status'),
      reconnect || !loadedMap.current ? simulationRequest<HouseMap>('map') : loadedMap.current,
    ]).then(([nextState, nextMap]) => {
      loadedMap.current = nextMap;
      setMap(nextMap);
      setState(nextState);
      setConnection('online');
    }).catch(() => {
      setConnection('offline');
    }).finally(() => {
      polling.current = null;
    });

    polling.current = request;
    return request;
  }, []);

  useFocusEffect(useCallback(() => {
    const poll = () => {
      if (!commanding.current) void refresh();
    };
    poll();
    const timer = setInterval(poll, 1000);
    return () => clearInterval(timer);
  }, [refresh]));

  const command = async (endpoint: string, body?: object) => {
    if (commanding.current) return;
    commanding.current = true;
    setBusy(true);
    setCommandError('');
    try {
      await polling.current;
      await simulationRequest(endpoint, {
        method: 'POST',
        ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
      });
    } catch {
      setCommandError('The command could not be completed. Try again.');
    } finally {
      await refresh();
      commanding.current = false;
      setBusy(false);
    }
  };

  const reconnect = async () => {
    setConnection('loading');
    await polling.current;
    await refresh(true);
  };

  const handleSignOut = async () => {
    if (signOutInProgress.current) return;
    signOutInProgress.current = true;
    setSigningOut(true);
    setSignOutError(false);
    try {
      await clearSession();
      setSignedIn(false);
    } catch {
      setSignOutError(true);
    } finally {
      signOutInProgress.current = false;
      setSigningOut(false);
    }
  };

  const manual = state?.mode === 'manual';
  const decision = state?.ai_decision;
  return (
    <AiryScreen>
      <Header title="MY Home" subtitle="AI Walking Air Purifier"
        action={<Button label={signingOut ? 'Signing Out...' : 'Sign Out'} variant="secondary"
          disabled={signingOut} onPress={handleSignOut} />} />
      <ScrollView contentContainerStyle={layout.list}>
        {signOutError && <Copy color={colors.red}>Unable to sign out. Try again.</Copy>}
        {connection !== 'online' || !map || !state ? (
          <ConnectionCard loading={connection === 'loading'} reconnect={reconnect} />
        ) : <>
          <DeviceStatus state={state} />
          <FloorPlan map={map} state={state} />
          <View style={layout.row}>
            <Copy size={17} bold>Room Air Quality</Copy>
            <Copy size={10} color={colors.muted}>µg/m³</Copy>
          </View>
          {map.rooms.map(room => <AirQuality key={room.id} room={room} state={state} />)}
          <Card style={styles.decision}>
            <Copy size={16} bold>AI Decision</Copy>
            <Copy size={10} color={colors.muted}>Selected Destination</Copy>
            <Copy size={20} bold color={colors.red}>{roomName(manual ? state.destination : decision?.target_room, '—')}</Copy>
            <Copy size={10} color={colors.muted}>Decision Reason</Copy>
            <Copy size={12}>{manual ? 'Manual Mode is active. Choose a destination below.'
              : decision ? reasons[decision.reason] ?? decision.reason.replaceAll('_', ' ')
              : 'Waiting for measurements and an AI decision.'}</Copy>
          </Card>
          {commandError !== '' && <Copy color={colors.red}>{commandError}</Copy>}
          <Operations map={map} state={state} busy={busy} command={command} />
        </>}
      </ScrollView>
    </AiryScreen>
  );
}

const styles = StyleSheet.create({
  system: { marginTop: 104, gap: 24 },
  systemCard: { paddingHorizontal: 24, paddingVertical: 30, gap: 15, alignItems: 'center' },
  systemIcon: { width: 64, height: 64, borderRadius: 32, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.55)' },
  systemGlyph: { width: 30, height: 30 },
  fullWidth: { alignSelf: 'stretch' },
  centerText: { textAlign: 'center' },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 7, paddingHorizontal: 11, paddingVertical: 6, borderRadius: 20, backgroundColor: colors.white },
  dot: { width: 6, height: 6, borderRadius: 3 },
  modeSelector: { ...layout.columns, borderRadius: 20, backgroundColor: colors.white },
  decision: { gap: 7 },
});
