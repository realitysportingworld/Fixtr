import { Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import { BracketTab } from '@/components/competition/BracketTab';
import { FixturesTab } from '@/components/competition/FixturesTab';
import { SettingsTab } from '@/components/competition/SettingsTab';
import { StatsTab } from '@/components/competition/StatsTab';
import { TableTab } from '@/components/competition/TableTab';
import { TeamsTab } from '@/components/competition/TeamsTab';
import type { CompetitionData } from '@/components/competition/types';
import { colors, ErrorBanner, Loading, space, StatusBadge } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { showError } from '@/lib/dialogs';
import { FORMAT_LABELS, playerStatsSupported, SPORT_LABELS } from '@/lib/format';
import { shareCompetition } from '@/lib/share';
import { useLoad } from '@/lib/useLoad';

type Tab = 'teams' | 'fixtures' | 'table' | 'bracket' | 'stats' | 'settings';

async function loadCompetition(id: string): Promise<Omit<CompetitionData, 'readOnly'>> {
  const [competition, teams, fixtures] = await Promise.all([
    api.getCompetition(id),
    api.listTeams(id),
    api.listFixtures(id),
  ]);
  const [standings, groups, stats] = await Promise.all([
    competition.format === 'league' || competition.format === 'league_phase' ? api.standings(id) : Promise.resolve([]),
    competition.format === 'group_knockout' ? api.groups(id) : Promise.resolve([]),
    playerStatsSupported(competition) && fixtures.length > 0 ? api.stats(id) : Promise.resolve(null),
  ]);
  return { competition, teams, fixtures, standings, groups, stats };
}

export default function CompetitionScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const { data, error, refreshing, reload, loading } = useLoad(() => loadCompetition(id));
  const [tab, setTab] = useState<Tab | null>(null);
  const [sharing, setSharing] = useState(false);

  if (loading) return <Loading />;
  if (!data) {
    return (
      <View style={{ padding: space.lg }}>
        <ErrorBanner message={error} />
      </View>
    );
  }

  const { competition, fixtures } = data;
  // Someone else's public competition: view only
  const readOnly = competition.owner_id !== user?.id;
  const tabs: { key: Tab; label: string }[] = [{ key: 'teams', label: 'Teams' }];
  if (competition.format !== 'knockout') tabs.push({ key: 'fixtures', label: 'Fixtures' });
  if (competition.format === 'league' || competition.format === 'league_phase') tabs.push({ key: 'table', label: 'Table' });
  if (competition.format === 'group_knockout') tabs.push({ key: 'table', label: 'Groups' });
  if (competition.format !== 'league') tabs.push({ key: 'bracket', label: 'Bracket' });
  if (data.stats) tabs.push({ key: 'stats', label: 'Stats' });
  if (!readOnly) tabs.push({ key: 'settings', label: 'Settings' });

  // Start on Teams while setting up, then on the most useful view once play begins
  const defaultTab: Tab =
    fixtures.length === 0 ? 'teams' : competition.format === 'knockout' ? 'bracket' : 'fixtures';
  const active = tab && tabs.some((t) => t.key === tab) ? tab : defaultTab;
  const ctx = { ...data, readOnly, reload };

  async function share() {
    setSharing(true);
    try {
      await shareCompetition(competition);
      if (!competition.share_url) await reload(); // the link was just turned on
    } catch (e) {
      showError(e);
    } finally {
      setSharing(false);
    }
  }

  return (
    <View style={{ flex: 1 }}>
      <Stack.Screen
        options={{
          title: competition.name,
          headerRight: readOnly
            ? undefined
            : () => (
                <Pressable onPress={share} disabled={sharing} hitSlop={12} accessibilityRole="button" accessibilityLabel="Share a link to this competition">
                  <Text style={[styles.share, sharing && { opacity: 0.5 }]}>Share</Text>
                </Pressable>
              ),
        }}
      />
      <View style={styles.header}>
        <View style={styles.metaRow}>
          <StatusBadge status={competition.status} />
          <Text style={styles.meta}>
            {SPORT_LABELS[competition.sport]} · {FORMAT_LABELS[competition.format]}
          </Text>
        </View>
        {readOnly ? (
          <Text style={styles.meta}>
            By @{competition.owner_username} · view only
          </Text>
        ) : null}
        {competition.description ? <Text style={styles.description}>{competition.description}</Text> : null}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.tabs}>
          {tabs.map((t) => (
            <Pressable
              key={t.key}
              onPress={() => setTab(t.key)}
              accessibilityRole="tab"
              accessibilityState={{ selected: active === t.key }}
              style={[styles.tab, active === t.key && styles.tabActive]}
            >
              <Text style={[styles.tabText, active === t.key && styles.tabTextActive]}>{t.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>
      <ScrollView
        contentContainerStyle={{ padding: space.lg, gap: space.md, paddingBottom: 48 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={reload} />}
        keyboardShouldPersistTaps="handled"
      >
        <ErrorBanner message={error} />
        {active === 'teams' && <TeamsTab {...ctx} />}
        {active === 'fixtures' && <FixturesTab {...ctx} />}
        {active === 'table' && <TableTab {...ctx} />}
        {active === 'bracket' && <BracketTab {...ctx} />}
        {active === 'stats' && <StatsTab {...ctx} />}
        {active === 'settings' && <SettingsTab {...ctx} />}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: space.lg, gap: space.sm },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  meta: { color: colors.muted, fontSize: 14 },
  description: { color: colors.ink, fontSize: 15 },
  tabs: { gap: space.sm, paddingVertical: space.sm },
  tab: { paddingHorizontal: space.lg, paddingVertical: space.sm, borderRadius: 999 },
  tabActive: { backgroundColor: colors.ink },
  tabText: { fontSize: 15, fontWeight: '600', color: colors.muted },
  tabTextActive: { color: colors.accent },
  share: { color: colors.primary, fontSize: 16, fontWeight: '700' },
});
