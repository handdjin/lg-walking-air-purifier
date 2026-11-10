
import { useEffect, useState } from 'react';
import {
  View,
  Text,
  Button,
  StyleSheet,
  Alert,
  Platform,
} from 'react-native';

// 맥북의 현재 IP 주소로 변경!
const SERVER_URL =
  Platform.OS === 'web'
    ? 'http://127.0.0.1:8000'
    : 'http://172.16.162.187:8000';

const roomNames: Record<string, string> = {
  living_room: '거실',
  kitchen: '주방',
  bedroom: '침실',
};

export default function HomeScreen() {
  const [currentRoom, setCurrentRoom] = useState('Loading...');

  // 현재 위치 조회
  const fetchStatus = async () => {
    try {
      const response = await fetch(`${SERVER_URL}/status`);

      if (!response.ok) {
        throw new Error('Failed to fetch status');
      }

      const data = await response.json();
      setCurrentRoom(data.current_room);
    } catch (error) {
      setCurrentRoom('Connection Failed');
      Alert.alert('Error', String(error));
    }
  };

  // 원하는 방으로 이동
  const moveToRoom = async (targetRoom: string) => {
    try {
      const response = await fetch(`${SERVER_URL}/move`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          target_room: targetRoom,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to move');
      }

      const data = await response.json();
      setCurrentRoom(data.current_room);
    } catch (error) {
      Alert.alert('Error', String(error));
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>My Home</Text>

      <Text style={styles.label}>Current Room</Text>
      <Text style={styles.room}>
        {roomNames[currentRoom] ?? currentRoom}
      </Text>

      <Button
        title="Move to Living Room"
        onPress={() => moveToRoom('living_room')}
      />

      <Button
        title="Move to Kitchen"
        onPress={() => moveToRoom('kitchen')}
      />

      <Button
        title="Move to Bedroom"
        onPress={() => moveToRoom('bedroom')}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    gap: 20,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
  },
  label: {
    fontSize: 18,
    color: '#666666',
  },
  room: {
    fontSize: 24,
    fontWeight: '600',
  },
});
