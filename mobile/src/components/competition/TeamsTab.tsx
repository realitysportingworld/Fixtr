import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { api } from '@/api/client';
import { Button, Card, colors, EmptyState, space } from '@/components/ui';
import { confirm, showError } from '@/lib/dialogs';

import type { TabProps } from './types';

/** Fewest teams the backend accepts when generating fixtures for this format. */
function minimumTeams({ format, num_groups, format_config }: TabProps['competition']): number {
  if (format === 'group_knockout') return 2 * (num_groups ?? 2);
  if (format === 'league_phase') {
    const { matches_per_team = 1, direct_qualifiers = 2, playoff_qualifiers = 0 } = format_config ?? {};
    return Math.max(2, matches_per_team + 1, direct_qualifiers + playoff_qualifiers);
  }
  return 2;
}

export function TeamsTab({ competition, teams, groups, readOnly, reload }: TabProps) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState<'add' | 'fill' | 'generate' | null>(null);
  const editable = competition.status === 'draft' && !readOnly;
  const full = teams.length >= competition.max_participants;
  const groupName = new Map(groups.map((g) => [g.id, g.name]));
  const minTeams = minimumTeams(competition);

  async function run(kind: 'add' | 'fill' | 'generate', fn: () => Promise<unknown>) {
    setBusy(kind);
    try {
      await fn();
      await reload();
    } catch (e) {
      showError(e);
    } finally {
      setBusy(null);
    }
  }

  async function addTeam() {
    if (!name.trim()) return;
    await run('add', () => api.addTeam(competition.id, name.trim()));
    setName('');
  }

  async function removeTeam(teamId: string, teamName: string) {
    if (await confirm('Remove team?', `Remove ${teamName} from this competition?`, 'Remove', true)) {
      await run('add', () => api.removeTeam(competition.id, teamId));
    }
  }

  async function generate() {
    const ok = await confirm(
      'Generate fixtures?',
      `This locks the ${teams.length} teams in and starts the competition.`,
      'Generate',
    );
    if (ok) await run('generate', () => api.generateFixtures(competition.id));
  }

  return (
    <View style={{ gap: space.md }}>
      <Text style={styles.count}>
        {teams.length} / {competition.max_participants} teams
      </Text>

      {editable && !full && (
        <View style={styles.addRow}>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder="Team name"
            placeholderTextColor={colors.muted}
            maxLength={100}
            style={styles.input}
            onSubmitEditing={addTeam}
            returnKeyType="done"
          />
          <Button title="Add" onPress={addTeam} loading={busy === 'add'} disabled={!name.trim()} />
        </View>
      )}

      {teams.length === 0 ? (
        <EmptyState
          title="No teams yet"
          body={readOnly ? undefined : 'Add teams by name, or fill every slot with placeholder names.'}
        />
      ) : (
        <Card style={{ paddingVertical: space.xs }}>
          {teams.map((t, i) => (
            <View key={t.id} style={[styles.team, i > 0 && styles.divider]}>
              <Pressable
                onPress={() => router.push({ pathname: '/competition/[id]/team/[teamId]', params: { id: competition.id, teamId: t.id } })}
                style={styles.teamLink}
                accessibilityRole="button"
                accessibilityHint="Opens the squad"
              >
                <Text style={styles.teamName}>{t.name}</Text>
                {t.group_id && groupName.get(t.group_id) ? (
                  <Text style={styles.group}>{groupName.get(t.group_id)}</Text>
                ) : null}
                <Text style={styles.squad}>Squad ›</Text>
              </Pressable>
              {editable && (
                <Pressable onPress={() => removeTeam(t.id, t.name)} hitSlop={12} accessibilityLabel={`Remove ${t.name}`}>
                  <Text style={styles.remove}>Remove</Text>
                </Pressable>
              )}
            </View>
          ))}
        </Card>
      )}

      {editable && (
        <View style={{ gap: space.sm }}>
          {!full && (
            <Button
              title={`Fill ${competition.max_participants - teams.length} empty slots`}
              variant="secondary"
              onPress={() => run('fill', () => api.fillTeams(competition.id))}
              loading={busy === 'fill'}
            />
          )}
          <Button
            title="Generate fixtures"
            onPress={generate}
            loading={busy === 'generate'}
            disabled={teams.length < minTeams}
          />
          {teams.length < minTeams && (
            <Text style={styles.hint}>Add at least {minTeams} teams to generate fixtures.</Text>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  count: { color: colors.muted, fontSize: 14, fontWeight: '600' },
  addRow: { flexDirection: 'row', gap: space.sm },
  input: {
    flex: 1,
    minHeight: 48,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    paddingHorizontal: space.md,
    fontSize: 16,
    color: colors.ink,
  },
  team: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.md, gap: space.sm },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  teamLink: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: space.sm, minHeight: 32 },
  teamName: { flex: 1, fontSize: 16, color: colors.ink },
  squad: { color: colors.primary, fontWeight: '600', fontSize: 14 },
  group: { fontSize: 13, color: colors.muted },
  remove: { color: colors.danger, fontWeight: '600' },
  hint: { color: colors.muted, fontSize: 13, textAlign: 'center' },
});
