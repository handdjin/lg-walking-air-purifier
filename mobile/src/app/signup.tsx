import { useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import { useRef, useState } from 'react';

import { AuthField, AuthForm } from '@/components/airy/auth-form';
import { Button, colors, Copy } from '@/components/airy/ui';
import { getCognitoAuth } from '@/lib/auth-session';

type Action = 'signup' | 'confirm' | 'resend';

const errorMessages: Record<string, string> = {
  UsernameExistsException: 'This account already exists. Sign in or verify your email.',
  InvalidPasswordException: 'Choose a password that meets the account password requirements.',
  CodeMismatchException: 'That code is incorrect. Check your email and try again.',
  ExpiredCodeException: 'That code has expired. Request a new code.',
  LimitExceededException: 'Too many attempts. Wait a moment and try again.',
  TooManyRequestsException: 'Too many attempts. Wait a moment and try again.',
  CodeDeliveryFailureException: 'The verification email could not be sent. Try again.',
  UserNotFoundException: 'We could not find an account for this email.',
};

const fallbackErrors: Record<Action, string> = {
  signup: 'Unable to create your account. Try again.',
  confirm: 'Unable to verify your email. Try again or sign in if it is already verified.',
  resend: 'Unable to resend the verification code. Try again.',
};

export default function SignUpScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const { verify } = useLocalSearchParams<{ verify?: string }>();
  const [verifying, setVerifying] = useState(verify === '1');
  const [email, setEmail] = useState('');
  const [registeredEmail, setRegisteredEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [code, setCode] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState<Action | null>(null);
  const requestInProgress = useRef(false);
  const busy = pending !== null;

  const backToSignIn = () => router.dismissTo('/login');

  const submit = async (action: Action) => {
    if (requestInProgress.current) return;
    const username = registeredEmail || email.trim();
    setStatus('');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(username)) {
      setError('Enter a valid email address.');
      return;
    }
    if (action === 'signup' && (!password || password !== confirmPassword)) {
      setError(password ? 'Passwords do not match.' : 'Enter a password.');
      return;
    }
    if (action === 'confirm' && !code.trim()) {
      setError('Enter the verification code.');
      return;
    }

    requestInProgress.current = true;
    setPending(action);
    setError('');
    try {
      const auth = await getCognitoAuth();
      if (action === 'signup') {
        const result = await auth.signUp({
          username,
          password,
          options: { userAttributes: { email: username } },
        });
        if (result.isSignUpComplete) {
          if (navigation.isFocused()) backToSignIn();
        } else if (result.nextStep.signUpStep === 'CONFIRM_SIGN_UP') {
          setRegisteredEmail(username);
          setPassword('');
          setConfirmPassword('');
          setVerifying(true);
          setStatus('We sent a verification code to your email.');
        } else {
          setError('Account setup requires an additional step.');
        }
      } else if (action === 'confirm') {
        const result = await auth.confirmSignUp({ username, confirmationCode: code.trim() });
        if (result.isSignUpComplete) {
          if (navigation.isFocused()) backToSignIn();
        } else {
          setError('Email verification requires an additional step.');
        }
      } else {
        await auth.resendSignUpCode({ username });
        setRegisteredEmail(username);
        setCode('');
        setStatus('A new verification code was sent to your email.');
      }
    } catch (cause) {
      const name = cause instanceof Error ? cause.name : '';
      setError(errorMessages[name] ?? fallbackErrors[action]);
    } finally {
      requestInProgress.current = false;
      setPending(null);
    }
  };

  return (
    <AuthForm title={verifying ? 'Verify your email' : 'Create your account'}
      footer={<Button label="Back to Sign In" variant="secondary" disabled={busy} onPress={backToSignIn} />}>
      {verifying && <Copy color={colors.muted}>
        {registeredEmail ? `Enter the code sent to ${registeredEmail}.` : 'Enter your email and verification code.'}
      </Copy>}
      {(!verifying || !registeredEmail) && (
        <AuthField label="Email" placeholder="you@example.com" value={email} onChangeText={setEmail}
          autoCapitalize="none" autoComplete="email" keyboardType="email-address" editable={!busy} />
      )}
      {verifying ? (
        <AuthField label="Verification Code" value={code} onChangeText={setCode}
          autoComplete="one-time-code" keyboardType="number-pad" editable={!busy}
          onSubmitEditing={() => submit('confirm')} />
      ) : <>
        <AuthField label="Password" value={password} onChangeText={setPassword}
          autoComplete="new-password" secureTextEntry editable={!busy} />
        <AuthField label="Confirm Password" value={confirmPassword} onChangeText={setConfirmPassword}
          autoComplete="off" secureTextEntry editable={!busy} onSubmitEditing={() => submit('signup')} />
      </>}
      {error !== '' && <Copy color={colors.red}>{error}</Copy>}
      {status !== '' && <Copy color={colors.muted}>{status}</Copy>}
      {verifying ? <>
        <Button label={pending === 'confirm' ? 'Verifying...' : 'Verify Email'} disabled={busy}
          onPress={() => submit('confirm')} />
        <Button label={pending === 'resend' ? 'Sending Code...' : 'Resend Code'} variant="secondary"
          disabled={busy} onPress={() => submit('resend')} />
      </> : <>
        <Button label={pending === 'signup' ? 'Creating Account...' : 'Sign Up'} disabled={busy}
          onPress={() => submit('signup')} />
        <Button label="Already have a code? Verify Email" variant="secondary" disabled={busy} onPress={() => {
          setError('');
          setPassword('');
          setConfirmPassword('');
          setVerifying(true);
        }} />
      </>}
    </AuthForm>
  );
}
