import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text } from 'react-native';

import { api } from '@/api/client';
import { AuthForm } from '@/components/AuthForm';
import { Button, colors, ErrorBanner, Field } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { errorText } from '@/lib/useLoad';

const MIN_PASSWORD = 8;

/** Forgot password: email a 6-digit code, then set a new password with it. */
export default function ForgotPassword() {
  const params = useLocalSearchParams<{ email?: string }>();
  const { signInWith } = useAuth();
  const [step, setStep] = useState<'email' | 'code'>('email');
  const [email, setEmail] = useState(params.email ?? '');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<'send' | 'reset' | null>(null);

  async function sendCode() {
    setBusy('send');
    setError(null);
    try {
      await api.forgotPassword(email.trim());
      setStep('code');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  async function reset() {
    setBusy('reset');
    setError(null);
    try {
      // Signs in straight away; the auth layout then moves on to the app
      await signInWith(await api.resetPassword(email.trim(), code.trim(), password));
    } catch (e) {
      setError(errorText(e));
      setBusy(null);
    }
  }

  if (step === 'email') {
    return (
      <AuthForm
        title="Forgot your password?"
        subtitle="We'll email you a code to set a new one."
        switchText="Remembered it?"
        switchHref="/login"
        switchLabel="Sign in"
      >
        <ErrorBanner message={error} />
        <Field
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          textContentType="emailAddress"
          onSubmitEditing={sendCode}
        />
        <Button title="Email me a code" onPress={sendCode} loading={busy === 'send'} disabled={!email.includes('@')} />
      </AuthForm>
    );
  }

  return (
    <AuthForm
      title="Check your email"
      subtitle={`If ${email.trim()} has an account, a 6-digit code is on its way. It expires in 15 minutes.`}
      switchText="Remembered it?"
      switchHref="/login"
      switchLabel="Sign in"
    >
      <ErrorBanner message={error} />
      <Field
        label="Code"
        value={code}
        onChangeText={(t) => setCode(t.replace(/\D/g, '').slice(0, 6))}
        keyboardType="number-pad"
        autoComplete="one-time-code"
        textContentType="oneTimeCode"
        maxLength={6}
      />
      <Field
        label="New password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="new-password"
        textContentType="newPassword"
        hint={`At least ${MIN_PASSWORD} characters`}
        onSubmitEditing={reset}
      />
      <Button
        title="Set new password"
        onPress={reset}
        loading={busy === 'reset'}
        disabled={code.length !== 6 || password.length < MIN_PASSWORD || busy !== null}
      />
      <Text style={styles.resend} onPress={busy ? undefined : sendCode} accessibilityRole="button">
        Didn't get it? Send another code
      </Text>
    </AuthForm>
  );
}

const styles = StyleSheet.create({
  resend: { color: colors.primary, fontWeight: '600', textAlign: 'center', fontSize: 15 },
});
