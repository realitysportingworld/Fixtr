import { router } from 'expo-router';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '@/api/client';
import { Button, Card, colors, EmptyState, ErrorBanner, Loading, SectionTitle, space, StatusBadge } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { FORMAT_LABELS, SPORT_LABELS } from '@/lib/format';
import { useLoad } from '@/lib/useLoad';

/** Magnifying glass drawn with views, so no icon font is needed. */
function SearchIcon() {
  return (
    <View style={styles.searchIcon} accessibilityElementsHidden importantForAccessibility="no">
      <View style={styles.searchLens} />
      <View style={styles.searchHandle} />
    </View>
  );
}

function Header({ username, count }: { username: string; count: number | null }) {
  return (
    <View style={{ gap: space.lg }}>
      <View style={styles.topRow}>
        <View>
          <Text style={styles.logo}>Fixtr</Text>
          <View style={styles.logoBar} />
        </View>
        <Pressable
          onPress={() => router.push('/account')}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel="Your account"
          style={({ pressed }) => [styles.avatar, pressed && { opacity: 0.8 }]}
        >
          <Text style={styles.avatarText}>{username.slice(0, 1).toUpperCase()}</Text>
        </Pressable>
      </View>

      <View style={{ gap: 2 }}>
        <Text style={styles.greeting} numberOfLines={1}>
          Hi {username}
        </Text>
        {count !== null && (
          <Text style={styles.subtitle}>
            {count === 0 ? 'Ready to start your first competition?' : `You organise ${count} ${count === 1 ? 'competition' : 'competitions'}`}
          </Text>
        )}
      </View>

      <Pressable
        onPress={() => router.push('/search')}
        accessibilityRole="search"
        accessibilityLabel="Find public competitions"
        style={({ pressed }) => [styles.searchBar, pressed && { opacity: 0.85 }]}
      >
        <SearchIcon />
        <Text style={styles.searchText}>Find public competitions</Text>
      </Pressable>
    </View>
  );
}

export default function Competitions() {
  const { user } = useAuth();
  const insets = useSafeAreaInsets();
  const { data, error, refreshing, reload, loading } = useLoad(async () => {
    const list = await api.listCompetitions();
    return list.sort((a, b) => b.created_at.localeCompare(a.created_at));
  });

  return (
    <View style={{ flex: 1 }}>
      {loading ? (
        <View style={{ paddingTop: insets.top + space.md, paddingHorizontal: space.lg, flex: 1 }}>
          <Header username={user?.username ?? ''} count={null} />
          <Loading />
        </View>
      ) : (
        <FlatList
          data={data ?? []}
          keyExtractor={(c) => c.id}
          contentContainerStyle={{ padding: space.lg, paddingTop: insets.top + space.md, gap: space.md, paddingBottom: 120 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={reload} />}
          ListHeaderComponent={
            <View style={{ gap: space.md }}>
              <Header username={user?.username ?? ''} count={data?.length ?? null} />
              <ErrorBanner message={error} />
              {data && data.length > 0 ? <SectionTitle>Your competitions</SectionTitle> : null}
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
  topRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 48 },
  logo: { fontSize: 28, fontWeight: '900', color: colors.ink, letterSpacing: -1 },
  logoBar: { width: 36, height: 5, borderRadius: 3, backgroundColor: colors.accent, marginTop: 2 },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.ink,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: colors.accent, fontSize: 18, fontWeight: '800' },
  greeting: { fontSize: 22, fontWeight: '700', color: colors.ink },
  subtitle: { fontSize: 15, color: colors.muted },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 48,
    paddingHorizontal: space.lg,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  searchText: { flex: 1, fontSize: 16, color: colors.muted },
  searchIcon: { width: 18, height: 18 },
  searchLens: { width: 13, height: 13, borderRadius: 7, borderWidth: 2, borderColor: colors.muted },
  searchHandle: {
    position: 'absolute',
    width: 7,
    height: 2,
    borderRadius: 1,
    backgroundColor: colors.muted,
    right: 0,
    bottom: 2,
    transform: [{ rotate: '45deg' }],
  },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.sm },
  name: { fontSize: 18, fontWeight: '700', color: colors.ink, flexShrink: 1 },
  meta: { fontSize: 14, color: colors.muted, marginTop: space.xs },
  fab: { position: 'absolute', left: space.lg, right: space.lg, bottom: 0 },
});
