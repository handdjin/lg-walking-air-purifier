
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  ScrollView,
  useWindowDimensions,
} from 'react-native';

const SERVER_URL =
  process.env.EXPO_PUBLIC_SERVER_URL ?? 'https://lg-air-purifier-demo.duckdns.org';

const API_KEY = process.env.EXPO_PUBLIC_API_KEY;

const API_HEADERS = {
  'X-API-Key': API_KEY ?? '',
};
type HouseMap = {
  width: number;
  height: number;
  grid: string[];
  rooms: {
    id: string;
    name: string;
    bounds: number[];
    target: number[];
  }[];
  start: number[];
};

type Mode = 'auto' | 'manual';

type SimulatorState = {
  mode: Mode;
  active_mode: Mode;
  current_room: string | null;
  room_name: string | null;
  position: number[];
  destination: string | null;
  status: string;
  remaining_steps: number;
  simulation_time_seconds: number;
  is_running: boolean;
  is_purifying: boolean;
  is_measuring: boolean;
  finished: boolean;
  observations: Record<string, { pm25: number | null; age_seconds: number | null }>;
  ai_prediction: { reference_minute: number; target_minute: number; status: string; predictions: Record<string, number | null> } | null;
  ai_decision: { action: string; target_room: string | null; reason: string } | null;
};

const roomNames: Record<string, string> = {
  living_room: '거실',
  kitchen: '주방',
  bedroom: '침실',
};

const tileColors: Record<string, string> = {
  '#': '#475569',
  '.': '#F1F5F9',
  'X': '#F59E0B',
  'D': '#86EFAC',
};
const decisionReasons: Record<string, string> = {
  all_predictions_below_threshold: '모든 방의 예측값이 기준 미만',
  no_reachable_candidate: '이동 가능한 후보 없음',
  current_room_selected: '현재 방 유지',
  highest_score: '예측 오염도와 이동 시간을 고려한 최적 방',
};
const clock = (minute: number) => `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`;

export default function HomeScreen() {
  const { width } = useWindowDimensions();

  const [houseMap, setHouseMap] = useState<HouseMap | null>(null);
  const [simState, setSimState] = useState<SimulatorState | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const requestRef = useRef(false);

  const revision = useRef(0);

  const refresh = useCallback(async (withMap = false) => {
    const version = revision.current;
    const response = await fetch(`${SERVER_URL}/status`, {
  headers: API_HEADERS,
});
    if (!response.ok) throw new Error('Status request failed');
    const state: SimulatorState = await response.json();
    if (withMap) {
      const mapResponse = await fetch(`${SERVER_URL}/map`, {
  headers: API_HEADERS,
});
      if (!mapResponse.ok) throw new Error('Map request failed');
      setHouseMap(await mapResponse.json());
    }
    if (version === revision.current) setSimState(state);
  }, []);

  const loadData = useCallback(async () => {
    if (requestRef.current) return;
    requestRef.current = true;
    setBusy(true);
    try {
      await refresh(true);
      setError('');
    } catch {
      setError('서버에 연결할 수 없습니다. Wi-Fi와 FastAPI를 확인해 주세요.');
    } finally {
      requestRef.current = false;
      setBusy(false);
      setLoading(false);
    }
  }, [refresh]);

  const command = async (endpoint: string, body?: object) => {
    if (requestRef.current) return;
    requestRef.current = true;
    setBusy(true);
    revision.current++;
    try {
      const response = await fetch(`${SERVER_URL}/${endpoint}`, {
        method: 'POST',
        headers: API_HEADERS,
        ...(body ? { headers: { ...API_HEADERS, 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
      });
      if (!response.ok) throw new Error('Command failed');
      await refresh();
      setError('');
    } catch {
      setError('명령 처리 또는 상태 조회에 실패했습니다.');
    } finally {
      requestRef.current = false;
      setBusy(false);
    }
  };

  useEffect(() => {
    const initialLoad = setTimeout(() => void loadData(), 0);
    let polling = false;
    const timer = setInterval(async () => {
      if (requestRef.current || polling) return;
      polling = true;
      try {
        await refresh();
      } catch {
        setError('상태 조회 실패: 마지막으로 받은 정보를 표시합니다.');
      } finally {
        polling = false;
      }
    }, 1000);
    return () => {
      clearTimeout(initialLoad);
      clearInterval(timer);
    };
  }, [loadData, refresh]);

  // 화면 너비에 맞춰 지도 크기 조정
  const cellSize = houseMap
    ? Math.min(24, (width - 48) / houseMap.width)
    : 20;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>My Home</Text>
      <Text style={styles.subtitle}>AI Walking Air Purifier</Text>

      {loading && <Text>Loading...</Text>}

      {error !== '' && (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
          <Pressable onPress={loadData} style={styles.retryButton}>
            <Text style={styles.retryText}>다시 연결</Text>
          </Pressable>
        </View>
      )}

      {houseMap && simState && (
        <>
          <Text style={styles.sectionTitle}>집 평면도</Text>

          <View style={styles.mapContainer}>
            {houseMap.grid.map((row, y) => (
              <View key={y} style={styles.mapRow}>
                {row.split('').map((tile, x) => {
                  const isPurifier =
                    simState.position[0] === x &&
                    simState.position[1] === y;

                  return (
                    <View
                      key={`${x}-${y}`}
                      style={[
                        styles.cell,
                        {
                          width: cellSize,
                          height: cellSize,
                          backgroundColor:
                            tileColors[tile] ?? '#FFFFFF',
                        },
                      ]}
                    >
                      {isPurifier && (
                        <View style={styles.purifier}>
                          <Text style={styles.purifierText}>P</Text>
                        </View>
                      )}
                    </View>
                  );
                })}
              </View>
            ))}
          </View>

          <View style={styles.legend}>
            <Text style={styles.legendText}>⬛ 벽</Text>
            <Text style={styles.legendText}>🟧 장애물</Text>
            <Text style={styles.legendText}>🟩 문</Text>
            <Text style={styles.legendText}>🔵 공기청정기</Text>
          </View>

          <View style={styles.statusBox}>
            <Text style={styles.label}>현재 위치</Text>
            <Text style={styles.currentRoom}>
              {simState.room_name ?? '통로'}
            </Text>

            <Text style={styles.detail}>
              좌표: [{simState.position.join(', ')}]
            </Text>
            <Text style={styles.detail}>
              상태: {
                simState.finished ? '종료' :
                !simState.is_running ? '일시정지' :
                simState.status === 'moving' ? '🔵 이동 중' :
                simState.is_measuring ? '🟡 측정 중' :
                simState.is_purifying ? '🟢 정화 중' :
                '⚪ 대기 중'
              }
            </Text>

            <Text style={styles.detail}>
              남은 이동 칸: {simState.remaining_steps}
            </Text>
            <Text style={styles.detail}>가상 시각: {clock(Math.floor(simState.simulation_time_seconds / 60))}</Text>
            <Text style={styles.detail}>이동 경로 목적지: {simState.remaining_steps > 0 && simState.destination ? roomNames[simState.destination] : '없음'}</Text>
            {simState.mode === 'auto' && <>
            <Text style={styles.detail}>최근 AI 선정 목적지: {simState.ai_decision?.target_room ? roomNames[simState.ai_decision.target_room] : simState.ai_decision ? '없음 (대기)' : '판단 전'}</Text>
            <Text style={styles.detail}>AI 판단 이유: {simState.ai_decision ? decisionReasons[simState.ai_decision.reason] ?? simState.ai_decision.reason : '측정 및 판단 대기'}</Text>
            </>}
          </View>
          
<Text style={styles.sectionTitle}>방별 공기질</Text>

<Text style={styles.sampleNotice}>
  {simState.ai_prediction?.status === 'ok'
    ? `AI 예측 기준 ${clock(simState.ai_prediction.reference_minute)} → ${clock(simState.ai_prediction.target_minute)}`
    : Object.values(simState.observations).some(reading => reading.pm25 == null)
      ? '초기 측정 필요' : 'AI 예측 대기 또는 예측 불가'}
</Text>
{Object.entries(roomNames).map(([roomId, name]) => {
  const measured = simState.observations?.[roomId]?.pm25;
  const predicted = simState.ai_prediction?.status === 'ok' ? simState.ai_prediction.predictions[roomId] : null;
  return (
    <View key={roomId} style={styles.airCard}>
      <Text style={styles.airRoomName}>{name}</Text>
      <View style={styles.airValues}>
        <View style={styles.airValueBox}>
          <Text style={styles.airLabel}>마지막 측정 PM2.5</Text>
          <Text style={styles.airNumber}>{measured == null ? '미측정' : measured.toFixed(1)}</Text>
          {measured != null && <Text style={styles.airUnit}>µg/m³ · {Math.floor((simState.observations[roomId].age_seconds ?? 0) / 60)}분 전 측정</Text>}
        </View>
        <View style={styles.airValueBox}>
          <Text style={styles.airLabel}>30분 후 AI 예측 PM2.5</Text>
          <Text style={styles.airNumber}>{predicted == null ? '예측 대기' : predicted.toFixed(1)}</Text>
          {predicted != null && <Text style={styles.airUnit}>µg/m³</Text>}
        </View>
      </View>
    </View>
  );
})}

          <Text style={styles.sectionTitle}>이동 모드</Text>
          <View style={styles.buttonContainer}>
            {(['auto', 'manual'] as const).map(mode => {
              const selected = simState.mode === mode;
              return (
                <Pressable key={mode} accessibilityRole="button"
                  accessibilityState={{ selected }}
                  disabled={busy || selected || simState.finished}
                  style={[styles.moveButton, !selected && styles.inactiveMode]}
                  onPress={() => command('mode', { mode })}>
                  <Text style={styles.buttonText}>{mode === 'auto' ? '자동' : '수동'}{selected ? ' ✓' : ''}</Text>
                </Pressable>
              );
            })}
          </View>
          {simState.mode !== simState.active_mode && (
            <Text style={styles.note}>현재 목적지 도착 후 선택한 모드로 전환됩니다.</Text>
          )}
          <View style={styles.buttonContainer}>
            {Object.entries(roomNames).map(([id, name]) => {
              const disabled = busy || simState.finished || simState.mode !== 'manual' || simState.active_mode !== 'manual';
              return (
                <Pressable key={id} accessibilityRole="button" disabled={disabled}
                  style={[styles.moveButton, disabled && styles.disabledButton]}
                  onPress={() => command('move', { target_room: id })}>
                  <Text style={styles.buttonText}>{name}</Text>
                </Pressable>
              );
            })}
          </View>
          <Text style={styles.sectionTitle}>시뮬레이션 제어</Text>

<View style={styles.buttonContainer}>
  <Pressable style={[styles.moveButton, (busy || simState.is_running || simState.finished) && styles.disabledButton]} disabled={busy || simState.is_running || simState.finished} onPress={() => command('start')}>
    <Text style={styles.buttonText}>▶ 시작</Text>
  </Pressable>
  <Pressable style={[styles.moveButton, (busy || !simState.is_running) && styles.disabledButton]} disabled={busy || !simState.is_running} onPress={() => command('pause')}>
    <Text style={styles.buttonText}>⏸ 일시정지</Text>
  </Pressable>
  <Pressable style={[styles.moveButton, busy && styles.disabledButton]} disabled={busy} onPress={() => command('reset')}>
    <Text style={styles.buttonText}>↺ 초기화</Text>
  </Pressable>
</View>
<Text style={styles.note}>{simState.mode === 'manual' ? (simState.is_running ? '이동할 방을 선택하세요.' : '방을 선택하고 시작을 누르면 이동합니다.') : '시작하면 초기 순찰 후 AI가 목적지를 선택합니다.'}</Text>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    alignItems: 'center',
    padding: 20,
    paddingTop: 55,
    backgroundColor: '#FFFFFF',
    gap: 12,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
  },
  subtitle: {
    fontSize: 14,
    color: '#64748B',
  },
  sectionTitle: {
    fontSize: 19,
    fontWeight: 'bold',
    marginTop: 14,
  },
  inactiveMode: { backgroundColor: '#475569' },
  disabledButton: {
  backgroundColor: '#94A3B8',
  },
  mapContainer: {
    borderWidth: 2,
    borderColor: '#CBD5E1',
    overflow: 'hidden',
  },
  mapRow: {
    flexDirection: 'row',
  },
  cell: {
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 0.25,
    borderColor: '#CBD5E1',
  },
  purifier: {
    width: '75%',
    height: '75%',
    borderRadius: 100,
    backgroundColor: '#2563EB',
    justifyContent: 'center',
    alignItems: 'center',
  },
  purifierText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: 'bold',
  },
  legend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 12,
  },
  legendText: {
    fontSize: 11,
  },
  statusBox: {
    width: '100%',
    padding: 16,
    backgroundColor: '#F1F5F9',
    borderRadius: 12,
    alignItems: 'center',
    gap: 5,
  },
  label: {
    fontSize: 14,
    color: '#64748B',
  },
  currentRoom: {
    fontSize: 23,
    fontWeight: 'bold',
  },
  detail: {
    fontSize: 13,
    color: '#475569',
  },
  buttonContainer: {
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
  },
  moveButton: {
    backgroundColor: '#2563EB',
    paddingVertical: 13,
    paddingHorizontal: 18,
    borderRadius: 9,
  },
  buttonText: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  note: {
    fontSize: 12,
    color: '#64748B',
    textAlign: 'center',
  },
  errorBox: {
    padding: 15,
    backgroundColor: '#FEE2E2',
    borderRadius: 10,
    alignItems: 'center',
    gap: 10,
  },
  errorText: {
    color: '#B91C1C',
    textAlign: 'center',
  },
  retryButton: {
    backgroundColor: '#475569',
    padding: 10,
    borderRadius: 8,
  },
  retryText: {
    color: '#FFFFFF',
  },
  sampleNotice: {
  fontSize: 12,
  color: '#D97706',
  textAlign: 'center',
},
airCard: {
  width: '100%',
  padding: 16,
  backgroundColor: '#F8FAFC',
  borderWidth: 1,
  borderColor: '#E2E8F0',
  borderRadius: 12,
  gap: 12,
},
airRoomName: {
  fontSize: 17,
  fontWeight: 'bold',
},
airValues: {
  flexDirection: 'row',
  gap: 12,
},
airValueBox: {
  flex: 1,
  gap: 6,
},
airLabel: {
  fontSize: 12,
  color: '#64748B',
},
airNumber: {
  fontSize: 22,
  fontWeight: 'bold',
  color: '#0F172A',
},
airUnit: {
  fontSize: 11,
  fontWeight: 'normal',
  color: '#64748B',
},
});
