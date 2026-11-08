
import { useEffect, useState } from 'react';
import {
  View,
  Text,
  Button,
  StyleSheet,
  Alert,
} from 'react-native';

// 자신의 MacBook IP 주소로 변경!
const SERVER_URL = 'http://192.168.0.3:8000';

export default function HomeScreen() {
  const [currentRoom, setCurrentRoom] = useState('Loading...');

  // 서버에서 현재 위치 가져오기
  const fetchStatus = async () => {
    try {
      const response = await fetch(`${SERVER_URL}/status`);

      if (!response.ok) {
        throw new Error('Failed to fetch status');
      }

      const data = await response.json();
      setCurrentRoom(data.current_room);
    } catch (error) {
      Alert.alert('Error', 'Cannot connect to server');
    }
  };

  // 서버에 이동 명령 보내기
  const moveToKitchen = async () => {
    try {
      const response = await fetch(`${SERVER_URL}/move`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error('Failed to move');
      }

      const data = await response.json();
      setCurrentRoom(data.current_room);
    } catch (error) {
      Alert.alert('Error', 'Move request failed');
    }
  };

  // 앱이 처음 실행될 때 서버 상태 확인
  useEffect(() => {
    fetchStatus();
  }, []);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>My Home</Text>

      <Text style={styles.label}>Current Room</Text>
      <Text style={styles.room}>{currentRoom}</Text>

      <Button
        title="Move to Kitchen"
        onPress={moveToKitchen}
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
