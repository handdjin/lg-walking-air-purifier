import { useState } from 'react';
import {
  View, Text, TextInput, Pressable,
  StyleSheet, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { signIn, confirmSignIn, fetchAuthSession } from 'aws-amplify/auth';
import * as SecureStore from 'expo-secure-store';

export default function LoginScreen() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
const [newPassword, setNewPassword] = useState('');
const [needsNewPassword, setNeedsNewPassword] = useState(false);
  const handleLogin = async () => {
    if (!email.trim() || !password) {
      setError('이메일과 비밀번호를 입력해 주세요.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const result = await signIn({
        username: email.trim(),
        password,
        options: {
          authFlowType: 'USER_PASSWORD_AUTH',
        },
      });

      if (result.isSignedIn) {
        const session = await fetchAuthSession();
        const token = session.tokens?.accessToken?.toString();

        if (!token) throw new Error('인증 토큰을 받지 못했습니다.');

        await SecureStore.setItemAsync('accessToken', token);
        router.replace('/');
      } else if (result.nextStep.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
        setNeedsNewPassword(true);
        setError('');
      } else {
        setError(`추가 인증이 필요합니다: ${result.nextStep.signInStep}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '로그인에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async () => {
  if (!newPassword) {
    setError('새 비밀번호를 입력해 주세요.');
    return;
  }

  setLoading(true);
  setError('');

  try {
    const result = await confirmSignIn({
      challengeResponse: newPassword,
    });

    if (result.isSignedIn) {
      const session = await fetchAuthSession();
      const token = session.tokens?.accessToken?.toString();

      if (!token) throw new Error('인증 토큰을 받지 못했습니다.');

      await SecureStore.setItemAsync('accessToken', token);
      router.replace('/');
    } else {
      setError(`추가 인증이 필요합니다: ${result.nextStep.signInStep}`);
    }
  } catch (err) {
    setError(err instanceof Error ? err.message : '비밀번호 변경에 실패했습니다.');
  } finally {
    setLoading(false);
  }
};
  return (
    <View style={styles.container}>
      <Text style={styles.title}>AI Walking Air Purifier</Text>
      <Text style={styles.subtitle}>Cognito 계정으로 로그인</Text>

      <TextInput
        style={styles.input}
        placeholder="이메일"
        autoCapitalize="none"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />

      <TextInput
        style={styles.input}
        placeholder="비밀번호"
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />

      {error !== '' && <Text style={styles.error}>{error}</Text>}

    {needsNewPassword && (
  <TextInput
    style={styles.input}
    placeholder="새 비밀번호"
    secureTextEntry
    value={newPassword}
    onChangeText={setNewPassword}
  />
)}
      <Pressable
  style={styles.button}
  onPress={needsNewPassword ? handleChangePassword : handleLogin}
  disabled={loading}
>
  {loading ? (
    <ActivityIndicator color="#FFFFFF" />
  ) : (
    <Text style={styles.buttonText}>
      {needsNewPassword ? '비밀번호 변경 후 로그인' : '로그인'}
    </Text>
  )}
</Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    padding: 24,
    backgroundColor: '#FFFFFF',
    gap: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    textAlign: 'center',
  },
  subtitle: {
    color: '#64748B',
    textAlign: 'center',
  },
  input: {
    borderWidth: 1,
    borderColor: '#CBD5E1',
    borderRadius: 10,
    padding: 14,
    fontSize: 16,
  },
  button: {
    backgroundColor: '#2563EB',
    padding: 15,
    borderRadius: 10,
    alignItems: 'center',
  },
  buttonText: {
    color: '#FFFFFF',
    fontWeight: 'bold',
  },
  error: {
    color: '#DC2626',
    textAlign: 'center',
  },
});