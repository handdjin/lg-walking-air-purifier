import { DarkTheme, DefaultTheme, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useColorScheme } from 'react-native';
import { useEffect, useState } from 'react';
import { Redirect, Slot, usePathname } from 'expo-router';
import * as SecureStore from 'expo-secure-store';
import { AnimatedSplashOverlay } from '@/components/animated-icon';
import AppTabs from '@/components/app-tabs';
import 'react-native-get-random-values';
import 'react-native-url-polyfill/auto';
import '../amplify-config';


SplashScreen.preventAutoHideAsync();

export default function TabLayout() {
  const colorScheme = useColorScheme();
  const pathname = usePathname();
const [isLoggedIn, setIsLoggedIn] = useState<boolean | null>(null);

useEffect(() => {
  SecureStore.getItemAsync('accessToken').then((token) => {
    setIsLoggedIn(!!token);
  });
}, [pathname]);
if (isLoggedIn === null) return null;

if (!isLoggedIn && pathname !== '/login') {
  return <Redirect href="/login" />;
}

if (isLoggedIn && pathname === '/login') {
  return <Redirect href="/" />;
}
  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <AnimatedSplashOverlay />
{pathname === '/login' ? <Slot /> : <AppTabs />}
    </ThemeProvider>
  );
}
