const server = process.env.EXPO_PUBLIC_SERVER_URL ?? 'https://lg-air-purifier-demo.duckdns.org';
const apiKey = process.env.EXPO_PUBLIC_API_KEY;

export async function simulationRequest<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${server}/${endpoint}`, {
    ...options,
    headers: {
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      ...options?.headers,
    },
    signal: options?.signal ?? AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new Error(`Server request failed (${response.status}).`);
  return response.json();
}

export type Room = { id: string; name: string; bounds: number[]; target: number[] };
export type HouseMap = { width: number; height: number; grid: string[]; rooms: Room[] };
export type Mode = 'auto' | 'manual';
export type SimulatorState = {
  mode: Mode;
  active_mode: Mode;
  current_room: string | null;
  position: number[];
  destination: string | null;
  status: string;
  remaining_steps: number;
  remaining_path?: number[][];
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
  living_room: 'Living Room', kitchen: 'Kitchen', bedroom: 'Bedroom',
};

export function roomName(id: string | null | undefined, fallback = 'Hallway') {
  return id ? roomNames[id] ?? id.replaceAll('_', ' ') : fallback;
}

export function formatTime(seconds: number) {
  return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
    .map(value => String(value).padStart(2, '0')).join(':');
}
