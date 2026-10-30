import { useState } from 'react';

import { AuthForm } from '@/components/AuthForm';
import { Button, ErrorBanner, Field } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { errorText } from '@/lib/useLoad';

export default function Register() {
  const { signUp } = useAuth();
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await signUp(email.trim(), username.trim(), password);
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  return (
    <AuthForm
      title="Create your account"
      subtitle="Run leagues and knockouts from your phone."
      switchText="Already have an account?"
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
      />
      <Field
        label="Username"
        value={username}
        onChangeText={setUsername}
        autoCapitalize="none"
        autoCorrect={false}
        textContentType="username"
        hint="3–30 characters: letters, numbers, _ . -"
      />
      <Field
        label="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="new-password"
        textContentType="newPassword"
        hint="At least 8 characters"
        onSubmitEditing={submit}
      />
      <Button
        title="Create account"
        onPress={submit}
        loading={busy}
        disabled={!email || !username || password.length < 8}
      />
    </AuthForm>
  );
}
