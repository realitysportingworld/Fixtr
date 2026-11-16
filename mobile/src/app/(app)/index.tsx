import { router, Stack } from 'expo-router';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '@/api/client';
import { Button, Card, colors, EmptyState, ErrorBanner, Loading, space, StatusBadge } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { FORMAT_LABELS, SPORT_LABELS } from '@/lib/format';
import { useLoad } from '@/lib/useLoad';

export default function Competitions() {
  const { user } = useAuth();
  const insets = useSafeAreaInsets();
  const { data, error, refreshing, reload, loading } = useLoad(async () => {
    const list = await api.listCompetitions();
    return list.sort((a, b) => b.created_at.localeCompare(a.created_at));
  });

  return (
    <View style={{ flex: 1 }}>
      <Stack.Screen
        options={{
          headerLeft: () => (
            <Pressable onPress={() => router.push('/search')} hitSlop={12} accessibilityLabel="Find public competitions">
              <Text style={styles.headerLink}>Search</Text>
            </Pressable>
          ),
          headerRight: () => (
            <Pressable onPress={() => router.push('/account')} hitSlop={12} accessibilityLabel="Your account">
              <Text style={styles.headerLink}>Account</Text>
            </Pressable>
          ),
        }}
      />
      {loading ? (
        <Loading />
      ) : (
        <FlatList
          data={data ?? []}
          keyExtractor={(c) => c.id}
          contentContainerStyle={{ padding: space.lg, gap: space.md, paddingBottom: 120 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={reload} />}
          ListHeaderComponent={
            <View style={{ gap: space.md }}>
              <Text style={styles.greeting}>Hi {user?.username}</Text>
              <ErrorBanner message={error} />
            </View>
          }
          ListEmptyComponent={
            error ? undefined : (
              <EmptyState title="No competitions yet" body="Create a league or knockout to get started." />
            )
          }
          renderItem={({ item }) => (
            <Pressable onPress={() => router.push({ pathname: '/competition/[id]', params: { id: item.id } })}>
              {({ pressed }) => (
                <Card style={pressed && { opacity: 0.85 }}>
                  <View style={styles.row}>
                    <Text style={styles.name} numberOfLines={1}>
                      {item.name}
                    </Text>
                    <StatusBadge status={item.status} />
                  </View>
                  <Text style={styles.meta}>
                    {SPORT_LABELS[item.sport]} · {FORMAT_LABELS[item.format]} · up to {item.max_participants} teams
                  </Text>
                </Card>
              )}
            </Pressable>
          )}
        />
      )}
      <View style={[styles.fab, { paddingBottom: insets.bottom + space.lg }]}>
        <Button title="+ New competition" onPress={() => router.push('/new')} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  greeting: { fontSize: 15, color: colors.muted },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.sm },
  name: { fontSize: 18, fontWeight: '700', color: colors.ink, flexShrink: 1 },
  meta: { fontSize: 14, color: colors.muted, marginTop: space.xs },
  headerLink: { color: colors.primary, fontWeight: '600', fontSize: 15 },
  fab: { position: 'absolute', left: space.lg, right: space.lg, bottom: 0 },
});
