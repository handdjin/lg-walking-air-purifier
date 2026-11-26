import { useRouter } from 'expo-router';
import { useContext, useState } from 'react';

import { AuthField, AuthForm } from '@/components/airy/auth-form';
import { Button, colors, Copy } from '@/components/airy/ui';
import { getCognitoAuth, saveSession, AuthStateContext } from '@/lib/auth-session';

export default function LoginScreen() {
  const router = useRouter();
  const setSignedIn = useContext(AuthStateContext);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [needsNewPassword, setNeedsNewPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [needsVerification, setNeedsVerification] = useState(false);

  const submit = async () => {
    if (loading) return;
    if (needsNewPassword ? !newPassword : !email.trim() || !password) {
      setError(needsNewPassword ? 'Enter a new password.' : 'Enter your email and password.');
      return;
    }
    setNeedsVerification(false);
    setLoading(true);
    setError('');
    try {
      const { confirmSignIn, signIn } = await getCognitoAuth();
      const result = needsNewPassword
        ? await confirmSignIn({ challengeResponse: newPassword })
        : await signIn({ username: email.trim(), password, options: { authFlowType: 'USER_PASSWORD_AUTH' } });
      if (result.isSignedIn) {
        await saveSession();
        setSignedIn(true);
      } else if (result.nextStep.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
        setNeedsNewPassword(true);
      } else if (result.nextStep.signInStep === 'CONFIRM_SIGN_UP') {
        setNeedsVerification(true);
      } else {
        setError('Your account requires an additional verification step.');
      }
    } catch (cause) {
      const name = cause instanceof Error ? cause.name : '';
      if (name === 'UserNotConfirmedException') {
        setNeedsVerification(true);
      } else if (name === 'NotAuthorizedException' || name === 'UserNotFoundException') {
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
    <AuthForm
      title={needsNewPassword ? 'Set a new password' : 'Welcome home'}
      introduction={<Copy size={22} bold>{'A little movement.\nA breath of fresh air.'}</Copy>}
      footer={!needsNewPassword && (
        <Button label="Don't have an account? Sign Up" variant="secondary" disabled={loading}
          onPress={() => router.push('./signup')} />
      )}
    >
      {needsNewPassword ? (
        <AuthField label="New Password" value={newPassword} onChangeText={setNewPassword}
          autoComplete="new-password" secureTextEntry editable={!loading} onSubmitEditing={submit} />
      ) : <>
        <AuthField label="Email" placeholder="you@example.com" value={email} onChangeText={setEmail}
          autoCapitalize="none" autoComplete="email" keyboardType="email-address" editable={!loading} />
        <AuthField label="Password" placeholder="••••••••••" value={password} onChangeText={setPassword}
          autoComplete="current-password" secureTextEntry editable={!loading} onSubmitEditing={submit} />
      </>}
      {error !== '' && <Copy color={colors.red}>{error}</Copy>}
      <Button label={loading ? 'Signing In...' : needsNewPassword ? 'Set Password and Sign In' : 'Sign In'}
        disabled={loading} onPress={submit} />
      {needsVerification && <>
        <Copy color={colors.red}>Verify your email before signing in.</Copy>
        <Button label="Verify Email" variant="secondary" disabled={loading}
          onPress={() => {
            setNeedsVerification(false);
            setPassword('');
            router.push('./signup?verify=1');
          }} />
      </>}
    </AuthForm>
  );
}
