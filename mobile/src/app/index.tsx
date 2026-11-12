
import { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  Platform,
  ScrollView,
  useWindowDimensions,
} from 'react-native';

const SERVER_URL =
  Platform.OS === 'web'
    ? 'http://127.0.0.1:8000'
    : 'http://192.168.0.3:8000';

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

type SimulatorState = {
  current_room: string | null;
  room_name: string | null;
  position: number[];
  destination: string | null;
  status: string;
  remaining_steps: number;
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

export default function HomeScreen() {
  const { width } = useWindowDimensions();

  const [houseMap, setHouseMap] = useState<HouseMap | null>(null);
  const [simState, setSimState] = useState<SimulatorState | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isStepping, setIsStepping] = useState(false);

const steppingRef = useRef(false);

  const loadData = async () => {
    try {
      const [mapResponse, statusResponse] = await Promise.all([
        fetch(`${SERVER_URL}/map`),
        fetch(`${SERVER_URL}/status`),
      ]);

      if (!mapResponse.ok || !statusResponse.ok) {
        throw new Error('Server request failed');
      }

      const mapData = await mapResponse.json();
      const statusData = await statusResponse.json();

      setHouseMap(mapData);
      setSimState(statusData);
      setError('');
    } catch (e) {
      setError('서버에 연결할 수 없습니다. Wi-Fi와 FastAPI를 확인해 주세요.');
    } finally {
      setLoading(false);
    }
  };

  const moveToRoom = async (targetRoom: string) => {
    try {
      const response = await fetch(`${SERVER_URL}/move`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ target_room: targetRoom }),
      });

      if (!response.ok) {
        throw new Error('Movement request failed');
      }

      const data = await response.json();
      setIsPlaying(false);
      setSimState(data);
      setError('');
    } catch (e) {
      setError('이동 명령을 전송하지 못했습니다.');
    }
  };

  
  // 공기청정기를 한 칸 이동
  const stepOnce = async () => {
    if (steppingRef.current) return;

    steppingRef.current = true;
    setIsStepping(true);

    try {
      const response = await fetch(`${SERVER_URL}/step`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error('Step request failed');
      }

      const data: SimulatorState = await response.json();
      setSimState(data);
      setError('');

      // 목적지에 도착하면 자동 정지
      if (data.remaining_steps === 0) {
        setIsPlaying(false);
      }
    } catch (e) {
      setIsPlaying(false);
      setError('이동 중 서버 연결에 실패했습니다.');
    } finally {
      steppingRef.current = false;
      setIsStepping(false);
    }
  };

  const resetSimulation = async () => {
  setIsPlaying(false);

  // 진행 중인 이동 요청이 끝날 때까지 초기화 방지
  if (steppingRef.current) return;

  try {
    const response = await fetch(`${SERVER_URL}/reset`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error('Reset request failed');
    }

    const data: SimulatorState = await response.json();
    setSimState(data);
    setError('');
  } catch (e) {
    setError('초기화에 실패했습니다.');
  }
};

  // 자동 이동: 0.7초마다 한 칸씩 이동
  useEffect(() => {
    if (!isPlaying || !simState || simState.remaining_steps === 0) {
      return;
    }

    const timer = setInterval(() => {
      void stepOnce();
    }, 700);

    return () => clearInterval(timer);
  }, [isPlaying, simState]);

  // 앱 실행 시 지도와 현재 상태 불러오기
  useEffect(() => {
    loadData();
  }, []);

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
              상태: {simState.status === 'moving' ? '이동 경로 설정됨' : '대기'}
            </Text>
            <Text style={styles.detail}>
              남은 이동 칸: {simState.remaining_steps}
            </Text>
          </View>

          <Text style={styles.sectionTitle}>이동 제어</Text>

<View style={styles.buttonContainer}>
  <Pressable
    style={[
      styles.moveButton,
      isPlaying && styles.disabledButton,
    ]}
    disabled={
      isPlaying ||
      isStepping ||
      simState.remaining_steps === 0
    }
    onPress={() => setIsPlaying(true)}
  >
    <Text style={styles.buttonText}>▶ 시작</Text>
  </Pressable>

  <Pressable
    style={[
      styles.moveButton,
      !isPlaying && styles.disabledButton,
    ]}
    disabled={!isPlaying}
    onPress={() => setIsPlaying(false)}
  >
    <Text style={styles.buttonText}>⏸ 일시정지</Text>
  </Pressable>
  <Pressable
  style={[
    styles.moveButton,
    isStepping && styles.disabledButton,
  ]}
  disabled={isStepping}
  onPress={resetSimulation}
  >
  <Text style={styles.buttonText}>↺ 초기화</Text>
  </Pressable>
</View>
          <Text style={styles.sectionTitle}>수동 이동</Text>

          <View style={styles.buttonContainer}>
            {Object.entries(roomNames).map(([id, name]) => (
              <Pressable
                key={id}
                style={styles.moveButton}
                onPress={() => moveToRoom(id)}
              >
                <Text style={styles.buttonText}>{name} 이동</Text>
              </Pressable>
            ))}
          </View>

          <Text style={styles.note}>
            이동할 방을 선택한 뒤 시작 버튼을 누르세요.
          </Text>
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
});
