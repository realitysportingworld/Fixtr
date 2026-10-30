import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { api } from '@/api/client';
import type { Competition } from '@/api/types';
import { Card, colors, EmptyState, ErrorBanner, Loading, space, StatusBadge } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { FORMAT_LABELS, SPORT_LABELS } from '@/lib/format';
import { errorText } from '@/lib/useLoad';

const DEBOUNCE_MS = 300;

export default function Search() {
  const { user } = useAuth();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Competition[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Search as the user types; an empty query lists the newest public competitions
  useEffect(() => {
    let live = true;
    const timer = setTimeout(async () => {
      try {
        const found = await api.searchPublic(query.trim());
        if (live) {
          setResults(found);
          setError(null);
        }
      } catch (e) {
        if (live) setError(errorText(e));
      }
    }, DEBOUNCE_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [query]);

  return (
    <View style={{ flex: 1 }}>
      <View style={styles.searchBar}>
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Competition or organiser name"
          placeholderTextColor={colors.muted}
          autoFocus
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="search"
          maxLength={100}
          style={styles.input}
          accessibilityLabel="Search public competitions"
        />
      </View>
      {results === null && !error ? (
        <Loading />
      ) : (
        <FlatList
          data={results ?? []}
          keyExtractor={(c) => c.id}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ padding: space.lg, paddingTop: 0, gap: space.md }}
          ListHeaderComponent={<ErrorBanner message={error} />}
          ListEmptyComponent={
            error ? undefined : (
              <EmptyState
                title={query.trim() ? 'No matches' : 'No public competitions yet'}
                body="Only competitions their organisers have made public show up here."
              />
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
                    {SPORT_LABELS[item.sport]} · {FORMAT_LABELS[item.format]}
                  </Text>
                  <Text style={styles.owner}>
                    {item.owner_id === user?.id ? 'Yours' : `by @${item.owner_username}`}
                  </Text>
                </Card>
              )}
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  searchBar: { padding: space.lg },
  input: {
    minHeight: 48,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    paddingHorizontal: space.md,
    fontSize: 16,
    color: colors.ink,
  },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.sm },
  name: { fontSize: 18, fontWeight: '700', color: colors.ink, flexShrink: 1 },
  meta: { fontSize: 14, color: colors.muted, marginTop: space.xs },
  owner: { fontSize: 13, color: colors.primary, fontWeight: '600', marginTop: 2 },
});
