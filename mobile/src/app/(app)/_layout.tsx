import { Redirect, Stack } from 'expo-router';

import { colors, Loading } from '@/components/ui';
import { useAuth } from '@/lib/auth';

export default function AppLayout() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Redirect href="/login" />;
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.bg },
        headerShadowVisible: false,
        headerTintColor: colors.ink,
        headerTitleStyle: { fontWeight: '700' },
        contentStyle: { backgroundColor: colors.bg },
      }}
    >
      <Stack.Screen name="index" options={{ title: 'Competitions' }} />
      <Stack.Screen name="new" options={{ title: 'New competition', presentation: 'modal' }} />
      <Stack.Screen name="search" options={{ title: 'Find competitions' }} />
      <Stack.Screen name="competition/[id]/index" options={{ title: '' }} />
      <Stack.Screen name="competition/[id]/result" options={{ title: 'Result', presentation: 'modal' }} />
    </Stack>
  );
}
