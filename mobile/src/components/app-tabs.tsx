import { Image } from 'expo-image';
import { Tabs, TabList, TabSlot, TabTrigger, type TabTriggerSlotProps } from 'expo-router/ui';
import { Pressable, StyleSheet, View } from 'react-native';
import { colors, Copy } from '@/components/airy/ui';

const icons = {
  Home: [require('@/assets/airy/HomeIconHistory.svg'), require('@/assets/airy/HomeIconHome.svg')],
  History: [require('@/assets/airy/HistoryIconHome.svg'), require('@/assets/airy/HistoryIconHistory.svg')],
};

function TabButton({ label, isFocused, onPress, onLongPress }: TabTriggerSlotProps & { label: keyof typeof icons }) {
  return (
    <Pressable onPress={onPress} onLongPress={onLongPress} accessibilityRole="tab" accessibilityState={{ selected: isFocused }} style={styles.tab}>
      <Image source={icons[label][isFocused ? 1 : 0]} style={styles.icon} />
      <Copy size={11} bold color={isFocused ? colors.red : colors.muted}>{label}</Copy>
    </Pressable>
  );
}

export default function AppTabs() {
  return (
    <Tabs style={styles.screen}>
      <TabSlot style={styles.tabs} />
      <TabList asChild>
        <View style={styles.bar}>
          <TabTrigger name="home" href="/" asChild><TabButton label="Home" /></TabTrigger>
          <TabTrigger name="history" href="/explore" asChild><TabButton label="History" /></TabTrigger>
        </View>
      </TabList>
    </Tabs>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.sky },
  tabs: { flex: 1 },
  bar: {
    flexDirection: 'row', marginHorizontal: 20, marginTop: 10, minHeight: 72, paddingHorizontal: 10,
    paddingVertical: 9, gap: 4, borderRadius: 28, borderWidth: 1, borderColor: 'rgba(255,255,255,0.9)',
    backgroundColor: colors.white, boxShadow: '0px 8px 12px rgba(56,110,128,0.1)',
  },
  tab: { flex: 1, alignItems: 'center', gap: 2, minHeight: 44 },
  icon: { width: 24, height: 24 },
});
