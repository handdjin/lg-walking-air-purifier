import * as SecureStore from 'expo-secure-store';
import { createContext } from 'react';
import { Platform } from 'react-native';

export const SignInContext = createContext<() => void>(() => {});

export async function getCognitoAuth() {
  await import('../amplify-config');
  return import('aws-amplify/auth');
}

export async function hasSavedSession() {
  if (Platform.OS === 'web') {
    const { fetchAuthSession } = await getCognitoAuth();
    return Boolean((await fetchAuthSession()).tokens?.accessToken);
  }
  return Boolean(await SecureStore.getItemAsync('accessToken'));
}

export async function saveSession() {
  const { fetchAuthSession } = await getCognitoAuth();
  const session = await fetchAuthSession();
  const token = session.tokens?.accessToken?.toString();
  if (!token) throw new Error('Access token unavailable.');
  if (Platform.OS !== 'web') await SecureStore.setItemAsync('accessToken', token);
}
