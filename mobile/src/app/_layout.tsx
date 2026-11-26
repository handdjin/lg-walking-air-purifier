import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import 'expo-crypto';
import 'react-native-get-random-values';
import 'react-native-url-polyfill/auto';

import { Backdrop, layout } from '@/components/airy/ui';
import { hasSavedSession, AuthStateContext } from '@/lib/auth-session';

void SplashScreen.preventAutoHideAsync();

const fonts = {
  AiryDisplay: require('@/assets/airy/DynaPuff.ttf'),
  AiryMedium: require('@/assets/airy/NotoSansKR-Medium.ttf'),
  AiryBold: require('@/assets/airy/NotoSansKR-Bold.ttf'),
};

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts(fonts);
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const ready = signedIn !== null && (fontsLoaded || fontError != null);

  useEffect(() => {
    void hasSavedSession().then(setSignedIn, () => setSignedIn(false));
  }, []);

  useEffect(() => {
    if (ready) void SplashScreen.hideAsync();
  }, [ready]);

  return (
    <View style={layout.screen}>
      <StatusBar style="dark" />
      {signedIn !== true && <Backdrop />}
      {ready && (
        <SafeAreaView style={{ flex: 1 }}>
          <AuthStateContext.Provider value={setSignedIn}>
            <Stack screenOptions={{ headerShown: false, animation: 'none', contentStyle: { backgroundColor: 'transparent' } }}>
              <Stack.Protected guard={signedIn === true}>
                <Stack.Screen name="(main)" />
              </Stack.Protected>
              <Stack.Protected guard={signedIn === false}>
                <Stack.Screen name="login" />
                <Stack.Screen name="signup" />
              </Stack.Protected>
            </Stack>
          </AuthStateContext.Provider>
        </SafeAreaView>
      )}
    </View>
  );
}
