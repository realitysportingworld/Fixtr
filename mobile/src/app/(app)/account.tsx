import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import { Button, Card, colors, ErrorBanner, Field, SectionTitle, space } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { confirm, showError } from '@/lib/dialogs';
import { errorText } from '@/lib/useLoad';

const MIN_PASSWORD = 8;

function Notice({ message }: { message: string | null }) {
  if (!message) return null;
  return <Text style={styles.notice}>{message}</Text>;
}

export default function AccountScreen() {
  const { user, setUser, signOut, forget } = useAuth();
  const [username, setUsername] = useState(user?.username ?? '');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [deletePassword, setDeletePassword] = useState('');
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const [notices, setNotices] = useState<Record<string, string | null>>({});

  if (!user) return null;

  async function run(section: string, fn: () => Promise<string | null | void>) {
    setBusy(section);
    setErrors((e) => ({ ...e, [section]: null }));
    setNotices((n) => ({ ...n, [section]: null }));
    try {
      const notice = await fn();
      if (notice) setNotices((n) => ({ ...n, [section]: notice }));
    } catch (e) {
      setErrors((x) => ({ ...x, [section]: errorText(e) }));
    } finally {
      setBusy(null);
    }
  }

  const saveUsername = () =>
    run('username', async () => {
      setUser(await api.updateMe({ username: username.trim() }));
      return 'Username saved.';
    });

  const changePassword = () =>
    run('password', async () => {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      return 'Password changed. Your other devices have been signed out.';
    });

  async function signOutOthers() {
    const ok = await confirm('Sign out other devices?', 'Every other phone or tablet signed in to this account will be signed out.', 'Sign out others');
    if (ok) {
      await run('sessions', async () => {
        await api.logoutEverywhere();
        return 'Other devices signed out.';
      });
    }
  }

  async function deleteAccount() {
    const ok = await confirm(
      'Delete your account?',
      'Your account and every competition you organise, with all their teams, results and stats, are deleted for good. This cannot be undone.',
      'Delete everything',
      true,
    );
    if (!ok) return;
    setBusy('delete');
    try {
      await api.deleteAccount(deletePassword);
      await forget();
    } catch (e) {
      showError(e);
      setBusy(null);
    }
  }

  const usernameChanged = username.trim() !== user.username && username.trim().length >= 3;

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <SectionTitle>Profile</SectionTitle>
      <Card style={{ gap: space.md }}>
        <View style={{ gap: 2 }}>
          <Text style={styles.label}>Email</Text>
          <Text style={styles.value}>{user.email}</Text>
        </View>
        <Field
          label="Username"
          value={username}
          onChangeText={setUsername}
          autoCapitalize="none"
          autoCorrect={false}
          maxLength={30}
          hint="Shown on competitions you make public. Letters, numbers, _ . and -"
        />
        <ErrorBanner message={errors.username ?? null} />
        <Notice message={notices.username ?? null} />
        <Button title="Save username" onPress={saveUsername} loading={busy === 'username'} disabled={!usernameChanged || busy !== null} />
      </Card>

      <SectionTitle>Password</SectionTitle>
      <Card style={{ gap: space.md }}>
        <Field
          label="Current password"
          value={currentPassword}
          onChangeText={setCurrentPassword}
          secureTextEntry
          autoComplete="current-password"
          textContentType="password"
        />
        <Field
          label="New password"
          value={newPassword}
          onChangeText={setNewPassword}
          secureTextEntry
          autoComplete="new-password"
          textContentType="newPassword"
          hint={`At least ${MIN_PASSWORD} characters`}
        />
        <ErrorBanner message={errors.password ?? null} />
        <Notice message={notices.password ?? null} />
        <Button
          title="Change password"
          onPress={changePassword}
          loading={busy === 'password'}
          disabled={!currentPassword || newPassword.length < MIN_PASSWORD || busy !== null}
        />
      </Card>

      <SectionTitle>Devices</SectionTitle>
      <Card style={{ gap: space.sm }}>
        <ErrorBanner message={errors.sessions ?? null} />
        <Notice message={notices.sessions ?? null} />
        <Button title="Sign out other devices" variant="secondary" onPress={signOutOthers} loading={busy === 'sessions'} disabled={busy !== null} />
        <Button title="Sign out" variant="secondary" onPress={signOut} disabled={busy !== null} />
      </Card>

      <SectionTitle>Danger zone</SectionTitle>
      <Card style={{ gap: space.md }}>
        {confirmingDelete ? (
          <>
            <Text style={styles.body}>Enter your password to delete your account and all your competitions.</Text>
            <Field
              label="Password"
              value={deletePassword}
              onChangeText={setDeletePassword}
              secureTextEntry
              autoComplete="current-password"
              textContentType="password"
            />
            <View style={{ flexDirection: 'row', gap: space.sm }}>
              <Button title="Cancel" variant="secondary" onPress={() => setConfirmingDelete(false)} style={{ flex: 1 }} />
              <Button
                title="Delete account"
                variant="danger"
                onPress={deleteAccount}
                loading={busy === 'delete'}
                disabled={!deletePassword || busy !== null}
                style={{ flex: 1 }}
              />
            </View>
          </>
        ) : (
          <Button title="Delete account" variant="danger" onPress={() => setConfirmingDelete(true)} />
        )}
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: space.lg, gap: space.md, paddingBottom: 48 },
  label: { fontSize: 13, fontWeight: '600', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5 },
  value: { fontSize: 16, color: colors.ink },
  body: { fontSize: 15, color: colors.ink },
  notice: { fontSize: 14, color: colors.primary, fontWeight: '600' },
});
