import type { PropsWithChildren, ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { AiryScreen, Brand, Card, colors, Copy } from './ui';

export function AuthForm({ title, children, introduction, footer }: PropsWithChildren<{
  title: string;
  introduction?: ReactNode;
  footer?: ReactNode;
}>) {
  return (
    <AiryScreen>
      <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.identity}>
            <Brand size={46}>LG Airy</Brand>
            <Copy size={14} color={colors.muted}>AI Walking Air Purifier</Copy>
            {introduction}
          </View>
          <Card style={styles.form}>
            <Copy size={20} bold>{title}</Copy>
            {children}
          </Card>
          {footer}
          <Copy size={12} color={colors.muted} style={styles.tagline}>Your home. Your air. In harmony.</Copy>
        </ScrollView>
      </KeyboardAvoidingView>
    </AiryScreen>
  );
}

export function AuthField({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <View style={styles.field}>
      <Copy size={12} bold>{label}</Copy>
      <TextInput {...props} accessibilityLabel={label} placeholderTextColor={colors.muted} style={styles.input} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { flexGrow: 1, paddingTop: 48, paddingHorizontal: 20, paddingBottom: 24, gap: 30 },
  identity: { gap: 12, paddingTop: 16, paddingBottom: 20 },
  form: { paddingHorizontal: 20, paddingVertical: 24, gap: 20 },
  field: { gap: 8 },
  input: {
    minHeight: 52, paddingHorizontal: 18, color: colors.ink, fontFamily: 'AiryMedium', fontSize: 14,
    backgroundColor: 'rgba(255,255,255,0.46)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.9)', borderRadius: 20,
  },
  tagline: { textAlign: 'center' },
});
