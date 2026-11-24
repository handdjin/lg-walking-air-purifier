import { useContext, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { Brand, Button, Card, colors, Copy } from '@/components/airy/ui';
import { getCognitoAuth, saveSession, SignInContext } from '@/lib/auth-session';

function SignInField({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <View style={styles.field}>
      <Copy size={12} bold>{label}</Copy>
      <TextInput {...props} accessibilityLabel={label} placeholderTextColor={colors.muted} style={styles.input} />
    </View>
  );
}

export default function LoginScreen() {
  const onSignedIn = useContext(SignInContext);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [needsNewPassword, setNeedsNewPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (loading) return;
    if (needsNewPassword ? !newPassword : !email.trim() || !password) {
      setError(needsNewPassword ? 'Enter a new password.' : 'Enter your email and password.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const { confirmSignIn, signIn } = await getCognitoAuth();
      const result = needsNewPassword
        ? await confirmSignIn({ challengeResponse: newPassword })
        : await signIn({ username: email.trim(), password, options: { authFlowType: 'USER_PASSWORD_AUTH' } });
      if (result.isSignedIn) {
        await saveSession();
        onSignedIn();
      } else if (result.nextStep.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
        setNeedsNewPassword(true);
      } else {
        setError('Your account requires an additional verification step.');
      }
    } catch (cause) {
      const name = cause instanceof Error ? cause.name : '';
      if (name === 'NotAuthorizedException' || name === 'UserNotFoundException') {
        setError('Check your email and password and try again.');
      } else if (name === 'InvalidPasswordException') {
        setError('Choose a password that meets your account’s password requirements.');
      } else {
        setError(needsNewPassword ? 'Unable to change your password. Try again.' : 'Unable to sign in. Try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.identity}>
          <Brand size={46}>LG Airy</Brand>
          <Copy size={14} color={colors.muted}>AI Walking Air Purifier</Copy>
          <Copy size={22} bold>{'A little movement.\nA breath of fresh air.'}</Copy>
        </View>
        <Card style={styles.form}>
          <Copy size={20} bold>{needsNewPassword ? 'Set a new password' : 'Welcome home'}</Copy>
          {!needsNewPassword && <>
            <SignInField label="Email" placeholder="you@example.com" value={email} onChangeText={setEmail}
              autoCapitalize="none" autoComplete="email" keyboardType="email-address" editable={!loading} />
            <SignInField label="Password" placeholder="••••••••••" value={password} onChangeText={setPassword}
              autoComplete="current-password" secureTextEntry editable={!loading} onSubmitEditing={submit} />
          </>}
          {needsNewPassword && <SignInField label="New Password" value={newPassword} onChangeText={setNewPassword}
            autoComplete="new-password" secureTextEntry editable={!loading} onSubmitEditing={submit} />}
          {error !== '' && <Copy color={colors.red}>{error}</Copy>}
          <Button label={loading ? 'Signing In...' : needsNewPassword ? 'Set Password and Sign In' : 'Sign In'}
            disabled={loading} onPress={submit} />
        </Card>
        <Copy size={12} color={colors.muted} style={styles.tagline}>Your home. Your air. In harmony.</Copy>
      </ScrollView>
    </KeyboardAvoidingView>
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
