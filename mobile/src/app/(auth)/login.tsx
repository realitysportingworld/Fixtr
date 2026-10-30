import { useState } from 'react';

import { AuthForm } from '@/components/AuthForm';
import { Button, ErrorBanner, Field } from '@/components/ui';
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
    </AuthForm>
  );
}
