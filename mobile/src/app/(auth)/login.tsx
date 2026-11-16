import { Link } from 'expo-router';
import { useState } from 'react';
import { StyleSheet } from 'react-native';

import { AuthForm } from '@/components/AuthForm';
import { Button, colors, ErrorBanner, Field } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { errorText } from '@/lib/useLoad';

export default function Login() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await signIn(email.trim(), password);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <AuthForm
      title="Welcome back"
      subtitle="Sign in to manage your competitions."
      switchText="New here?"
      switchHref="/register"
      switchLabel="Create an account"
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
      />
      <Field
        label="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="current-password"
        textContentType="password"
        onSubmitEditing={submit}
      />
      <Button title="Sign in" onPress={submit} loading={busy} disabled={!email || !password} />
      <Link href={{ pathname: '/forgot', params: email.trim() ? { email: email.trim() } : {} }} style={styles.forgot}>
        Forgot password?
      </Link>
    </AuthForm>
  );
}

const styles = StyleSheet.create({
  forgot: { color: colors.primary, fontWeight: '600', textAlign: 'center', fontSize: 15 },
});
