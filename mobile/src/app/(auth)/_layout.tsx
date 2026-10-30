import { Redirect, Stack } from 'expo-router';

import { colors, Loading } from '@/components/ui';
import { useAuth } from '@/lib/auth';

export default function AuthLayout() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (user) return <Redirect href="/" />;
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }} />;
}
