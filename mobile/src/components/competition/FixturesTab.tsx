import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { Competition, Fixture } from '@/api/types';
import { useDateTimePicker } from '@/components/DateTimePicker';
import { Button, Card, colors, EmptyState, Field, SectionTitle, space } from '@/components/ui';
import { confirm, showError } from '@/lib/dialogs';
import { fixtureWinner, formatKickoff, hasStageThenKnockout } from '@/lib/format';

import { teamNamer, type TabProps } from './types';

export function openResult(competitionId: string, fixtureId: string) {
  router.push({ pathname: '/competition/[id]/result', params: { id: competitionId, fixtureId } });
}

/**
 * Whether a fixture's result can be entered or edited right now. The backend
 * enforces all of this too; here it just decides what's tappable.
 */
export function canEnterResult(competition: Competition, fixtures: Fixture[], f: Fixture, readOnly: boolean) {
  if (readOnly || f.is_bye || competition.status === 'cancelled') return false;
  const knockoutStarted = fixtures.some((x) => x.knockout_round);
  if (!f.knockout_round && hasStageThenKnockout(competition) && knockoutStarted) return false;
  if (f.leg === 2) {
    const firstLeg = fixtures.find(
      (x) => x.leg === 1 && x.round_number === f.round_number && x.bracket_position === f.bracket_position,
    );
    return firstLeg?.status === 'completed';
  }
  return true;
}

function statusText(f: Fixture, tappable: boolean): string {
  if (f.is_bye) return 'Bye';
  if (f.home_score == null) return tappable ? 'Enter ›' : '';
  // A single knockout match that finished level was settled by a tiebreak
  if (f.knockout_round && !f.leg && f.home_score === f.away_score) return 'Pens';
  return 'FT';
}

export function FixtureRow({
  fixture, name, onPress, tag, showDate = true,
}: {
  fixture: Fixture;
  name: (id: string | null) => string;
  onPress?: () => void;
  tag?: string;
  showDate?: boolean; // off when the section header already shows the shared date
}) {
  const winner = fixtureWinner(fixture);
  const side = (teamId: string | null, score: number | null) => {
    const won = teamId != null && winner === teamId;
    return (
      <View style={styles.side}>
        <Text style={[styles.team, won && styles.winner, !teamId && styles.bye]} numberOfLines={1}>
          {name(teamId)}
        </Text>
        <Text style={[styles.score, won && styles.winner]}>{fixture.is_bye ? '' : (score ?? '–')}</Text>
      </View>
    );
  };

  return (
    <Pressable onPress={onPress} disabled={!onPress} accessibilityRole={onPress ? 'button' : undefined}>
      {({ pressed }) => (
        <View style={[styles.row, pressed && { backgroundColor: colors.bg }]}>
          <View style={{ flex: 1, gap: 2 }}>
            {showDate && fixture.scheduled_at ? (
              <Text style={styles.kickoff}>{formatKickoff(fixture.scheduled_at)}</Text>
            ) : null}
            {side(fixture.home_team_id, fixture.home_score)}
            {side(fixture.away_team_id, fixture.away_score)}
          </View>
          <View style={styles.right}>
            {tag ? <Text style={styles.tag}>{tag}</Text> : null}
            <Text style={styles.status}>{statusText(fixture, !!onPress)}</Text>
          </View>
        </View>
      )}
    </Pressable>
  );
}

function AdvancePanel({ competition, reload }: { competition: Competition; reload: () => Promise<void> }) {
  const [perGroup, setPerGroup] = useState('2');
  const [busy, setBusy] = useState(false);
  const leaguePhase = competition.format === 'league_phase';
  const { direct_qualifiers: direct = 0, playoff_qualifiers: playoff = 0 } = competition.format_config ?? {};

  const summary = leaguePhase
    ? playoff > 0
      ? `The top ${direct} go straight through; ${direct + 1}–${direct + playoff} meet in the knockout play-off. ` +
        'League phase results lock after this.'
      : `The top ${direct} go into the knockout. League phase results lock after this.`
    : `The top ${perGroup || '?'} of each group advance. Group results lock after this.`;

  async function advance() {
    if (!(await confirm('Start knockout?', summary, 'Start'))) return;
    setBusy(true);
    try {
      await api.advanceToKnockout(competition.id, Number.parseInt(perGroup, 10) || 0);
      await reload();
    } catch (e) {
      showError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card style={{ gap: space.md, borderColor: colors.primary }}>
      <Text style={styles.panelTitle}>{leaguePhase ? 'League phase complete' : 'Group stage complete'}</Text>
      {leaguePhase ? (
        <Text style={styles.panelBody}>{summary}</Text>
      ) : (
        <Field label="Teams advancing per group" value={perGroup} onChangeText={setPerGroup} keyboardType="number-pad" />
      )}
      <Button title="Start knockout stage" onPress={advance} loading={busy} />
    </Card>
  );
}

/** Date shared by every match in a section, if they all have the same one. */
function sharedDate(items: Fixture[]): string | null {
  const first = items[0]?.scheduled_at ?? null;
  return first && items.every((f) => f.scheduled_at === first) ? first : null;
}

export function FixturesTab({ competition, teams, fixtures, groups, readOnly, reload }: TabProps) {
  const { pick, picker } = useDateTimePicker();
  const [dating, setDating] = useState<string | null>(null);

  if (fixtures.length === 0) {
    return (
      <EmptyState
        title="No fixtures yet"
        body={readOnly ? undefined : 'Add teams, then generate fixtures from the Teams tab.'}
      />
    );
  }

  const name = teamNamer(teams);
  const groupName = new Map(groups.map((g) => [g.id, g.name]));
  const stageFixtures = fixtures.filter((f) => !f.knockout_round);
  const knockoutStarted = fixtures.some((f) => f.knockout_round);
  const canAdvance =
    !readOnly &&
    hasStageThenKnockout(competition) &&
    competition.status === 'active' &&
    !knockoutStarted &&
    stageFixtures.length > 0 &&
    stageFixtures.every((f) => f.status === 'completed');
  const roundWord = competition.format === 'league_phase' ? 'Matchday' : 'Round';

  const sections: { title: string; items: Fixture[] }[] = [];
  for (const f of fixtures) {
    const title = f.knockout_round ?? `${roundWord} ${f.round_number}`;
    const last = sections[sections.length - 1];
    if (last?.title === title) last.items.push(f);
    else sections.push({ title, items: [f] });
  }

  const remaining = fixtures.filter((f) => f.status !== 'completed').length;
  const canSchedule = !readOnly && competition.status !== 'cancelled';

  // One date and time for every match in the round (e.g. "all of Matchday 3: Sat 15:00")
  async function scheduleSection(title: string, items: Fixture[]) {
    const matches = items.filter((f) => !f.is_bye);
    const current = matches.find((f) => f.scheduled_at)?.scheduled_at;
    const at = await pick(current ? new Date(current) : null);
    if (!at) return;
    setDating(title);
    try {
      await api.scheduleFixtures(competition.id, matches.map((f) => ({ fixtureId: f.id, at })));
      await reload();
    } catch (e) {
      showError(e);
    } finally {
      setDating(null);
    }
  }

  return (
    <View style={{ gap: space.sm }}>
      <Text style={styles.summary}>
        {remaining === 0 ? 'All matches played' : `${remaining} of ${fixtures.length} matches to play`}
      </Text>
      {canAdvance && <AdvancePanel competition={competition} reload={reload} />}
      {sections.map((s) => {
        const shared = sharedDate(s.items);
        const open = s.items.some((f) => !f.is_bye && f.status !== 'completed');
        return (
        <View key={s.title} style={{ gap: space.sm }}>
          <View style={styles.sectionHead}>
            <View style={{ flex: 1 }}>
              <SectionTitle>{s.title}</SectionTitle>
              {shared ? <Text style={styles.kickoff}>{formatKickoff(shared)}</Text> : null}
            </View>
            {canSchedule && open && (
              <Pressable
                onPress={() => scheduleSection(s.title, s.items)}
                disabled={dating !== null}
                hitSlop={8}
                accessibilityRole="button"
                accessibilityLabel={`Set date for ${s.title}`}
              >
                <Text style={styles.sectionLink}>{dating === s.title ? 'Saving…' : shared ? 'Change date' : 'Set date'}</Text>
              </Pressable>
            )}
          </View>
          <Card style={{ padding: 0, overflow: 'hidden' }}>
            {s.items.map((f, i) => (
              <View key={f.id} style={i > 0 && styles.divider}>
                <FixtureRow
                  fixture={f}
                  name={name}
                  showDate={!shared}
                  tag={f.leg ? `Leg ${f.leg}` : f.group_id ? groupName.get(f.group_id) : undefined}
                  onPress={
                    canEnterResult(competition, fixtures, f, readOnly) ? () => openResult(competition.id, f.id) : undefined
                  }
                />
              </View>
            ))}
          </Card>
        </View>
        );
      })}
      {picker}
    </View>
  );
}

const styles = StyleSheet.create({
  summary: { color: colors.muted, fontSize: 14, fontWeight: '600' },
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.lg, paddingVertical: space.md, gap: space.md },
  side: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  team: { flex: 1, fontSize: 16, color: colors.ink },
  score: { fontSize: 16, fontWeight: '700', color: colors.ink, minWidth: 28, textAlign: 'right', fontVariant: ['tabular-nums'] },
  winner: { fontWeight: '800', color: colors.winner },
  bye: { color: colors.muted, fontStyle: 'italic' },
  right: { alignItems: 'flex-end', gap: 4, minWidth: 56 },
  tag: { fontSize: 12, color: colors.muted },
  status: { fontSize: 13, fontWeight: '600', color: colors.primary },
  kickoff: { fontSize: 12, color: colors.muted, fontWeight: '600' },
  sectionHead: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  sectionLink: { color: colors.primary, fontWeight: '600', fontSize: 14 },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  panelTitle: { fontSize: 17, fontWeight: '700', color: colors.ink },
  panelBody: { fontSize: 15, color: colors.ink },
});
