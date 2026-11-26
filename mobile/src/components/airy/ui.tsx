import { Image } from 'expo-image';
import type { PropsWithChildren, ReactNode } from 'react';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Pressable, StyleSheet, Text, View, type StyleProp, type TextStyle, type ViewStyle } from 'react-native';

export const colors = {
  sky: '#def6ff', ink: '#213845', muted: '#526d78', red: '#a50034',
  blue: '#2763a6', gold: '#926009', green: '#23725a', purple: '#7354a3',
  white: 'rgba(255,255,255,0.65)',
};

export function Copy({ children, size = 13, bold = false, color = colors.ink, style }: PropsWithChildren<{
  size?: number; bold?: boolean; color?: string; style?: StyleProp<TextStyle>;
}>) {
  return <Text style={[{ fontFamily: bold ? 'AiryBold' : 'AiryMedium', color, fontSize: size, lineHeight: Math.ceil(size * 1.45) }, style]}>{children}</Text>;
}

export function Brand({ children, size = 28 }: PropsWithChildren<{ size?: number }>) {
  return <Text accessibilityRole="header" style={{ fontFamily: 'AiryDisplay', color: colors.red, fontSize: size }}>{children}</Text>;
}

export function Backdrop({ top = 85 }: { top?: number }) {
  return <Image accessibilityIgnoresInvertColors source={require('@/assets/airy/AirBubbleBackdrop.svg')} style={[styles.backdrop, { top }]} />;
}

export function AiryScreen({ children }: PropsWithChildren) {
  const { top } = useSafeAreaInsets();
  return (
    <View style={layout.screen}>
      <Backdrop top={85 - top} />
      {children}
    </View>
  );
}

export function Header({ title, subtitle, action }: { title: string; subtitle: string; action?: ReactNode }) {
  return (
    <View style={styles.header}>
      <Copy size={10} color={colors.red} bold>LG Airy / ThinQ</Copy>
      <View style={layout.row}>
        <Brand>{title}</Brand>
        {action}
      </View>
      <Copy color={colors.muted}>{subtitle}</Copy>
    </View>
  );
}

export function Card({ children, style }: PropsWithChildren<{ style?: StyleProp<ViewStyle> }>) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Button({ label, onPress, disabled = false, selected, variant = 'primary', compact = false, style }: {
  label: string; onPress?: () => void; disabled?: boolean; selected?: boolean;
  variant?: 'primary' | 'secondary'; compact?: boolean; style?: StyleProp<ViewStyle>;
}) {
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ disabled, selected }} disabled={disabled} onPress={onPress}
      style={({ pressed }) => [styles.button, compact && styles.compact, variant === 'secondary' && styles.secondary,
        disabled && styles.disabled, pressed && styles.pressed, style]}>
      <Copy size={compact ? 12 : 13} bold color={disabled ? '#607984' : variant === 'primary' ? '#fff' : colors.red}
        style={styles.center}>{label}</Copy>
    </Pressable>
  );
}

export const layout = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.sky, overflow: 'hidden' },
  list: { paddingHorizontal: 20, paddingBottom: 24, gap: 14 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  columns: { flexDirection: 'row', gap: 10 },
  column: { flex: 1, gap: 4 },
});

const styles = StyleSheet.create({
  backdrop: { position: 'absolute', width: 210, height: 210, right: -72 },
  header: { paddingHorizontal: 24, paddingTop: 4, paddingBottom: 18, gap: 6 },
  card: {
    backgroundColor: 'rgba(255,255,255,0.46)', borderColor: 'rgba(255,255,255,0.9)', borderWidth: 1,
    borderRadius: 24, paddingHorizontal: 18, paddingVertical: 16, gap: 12,
    boxShadow: '0px 8px 24px -5px rgba(56,110,128,0.12)',
  },
  button: { minHeight: 48, paddingHorizontal: 12, justifyContent: 'center', alignItems: 'center', borderRadius: 24, backgroundColor: colors.red },
  compact: { minHeight: 38, paddingHorizontal: 6, flex: 1 },
  secondary: { backgroundColor: colors.white },
  disabled: { backgroundColor: '#d8e9ef' },
  pressed: { opacity: 0.75 },
  center: { textAlign: 'center' },
});
