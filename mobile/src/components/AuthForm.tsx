import { Link } from 'expo-router';
import { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors, space } from '@/components/ui';

/** Shared shell for the login and register screens. */
export function AuthForm({
  title, subtitle, children, switchText, switchHref, switchLabel,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  switchText: string;
  switchHref: '/login' | '/register';
  switchLabel: string;
}) {
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
          <View style={styles.brand}>
            <Text style={styles.logo}>CompApp</Text>
            <View style={styles.logoBar} />
          </View>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
          <View style={{ gap: space.lg, marginTop: space.xl }}>{children}</View>
          <Text style={styles.switch}>
            {switchText}{' '}
            <Link href={switchHref} replace style={styles.switchLink}>
              {switchLabel}
            </Link>
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, justifyContent: 'center', padding: space.xl },
  brand: { marginBottom: 40 },
  logo: { fontSize: 34, fontWeight: '900', color: colors.ink, letterSpacing: -1 },
  logoBar: { width: 48, height: 6, borderRadius: 3, backgroundColor: colors.accent, marginTop: space.xs },
  title: { fontSize: 24, fontWeight: '700', color: colors.ink },
  subtitle: { fontSize: 15, color: colors.muted, marginTop: space.xs },
  switch: { textAlign: 'center', color: colors.muted, marginTop: space.xl, fontSize: 15 },
  switchLink: { color: colors.primary, fontWeight: '700' },
});
