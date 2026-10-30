import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { Fixture } from '@/api/types';
import { Card, colors, EmptyState, space } from '@/components/ui';
import { fixtureWinner } from '@/lib/format';

import { canEnterResult, FixtureRow, openResult } from './FixturesTab';
import { teamNamer, type TabProps } from './types';

const SLOT_HEIGHT = 110; // vertical space per first-round tie
const COLUMN_WIDTH = 220;

// Same labels as get_knockout_round_label in backend/app/services/fixture_generator.py
function roundLabel(teamsInRound: number): string {
  return { 2: 'Final', 4: 'Semi-Final', 8: 'Quarter-Final' }[teamsInRound] ?? `Round of ${teamsInRound}`;
}

type Tie = Fixture[]; // one match, or [leg 1, leg 2]

interface Round {
  label: string;
  ties: (Tie | null)[]; // null = not drawn yet (previous round unfinished)
}

/** Played rounds grouped into ties, plus empty placeholder rounds down to the final. */
function buildRounds(fixtures: Fixture[]): Round[] {
  const byRound = new Map<number, Map<number, Fixture[]>>();
  for (const f of fixtures) {
    if (!f.knockout_round) continue;
    const ties = byRound.get(f.round_number) ?? new Map<number, Fixture[]>();
    const position = f.bracket_position ?? 0;
    ties.set(position, [...(ties.get(position) ?? []), f].sort((a, b) => (a.leg ?? 0) - (b.leg ?? 0)));
    byRound.set(f.round_number, ties);
  }
  const rounds: Round[] = [...byRound.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, ties]) => {
      const ordered = [...ties.entries()].sort(([a], [b]) => a - b).map(([, tie]) => tie);
      return { label: ordered[0][0].knockout_round!, ties: ordered };
    });
  let size = rounds.length ? rounds[rounds.length - 1].ties.length : 0;
  while (size > 1) {
    size = Math.ceil(size / 2);
    rounds.push({ label: roundLabel(size * 2), ties: Array(size).fill(null) });
  }
  return rounds;
}

const tieWinner = (tie: Tie) => fixtureWinner(tie[tie.length - 1]);

/** Two-legged tie: per-leg scores and aggregate for both teams. */
function TwoLegCard({
  tie, name, onLeg,
}: {
  tie: Tie;
  name: (id: string | null) => string;
  onLeg: (f: Fixture) => (() => void) | undefined;
}) {
  const [leg1, leg2] = tie;
  const a = leg1.home_team_id; // leg 2's away side
  const b = leg1.away_team_id;
  const winner = tieWinner(tie);
  const aggA = (leg1.home_score ?? 0) + (leg2.away_score ?? 0);
  const aggB = (leg1.away_score ?? 0) + (leg2.home_score ?? 0);
  const bothPlayed = leg1.home_score != null && leg2.home_score != null;
  const score = (n: number | null) => (n == null ? '–' : n);

  const row = (team: string | null, s1: number | null, s2: number | null, agg: number) => {
    const won = team != null && winner === team;
    return (
      <View style={styles.legRow}>
        <Text style={[styles.legTeam, won && styles.winner]} numberOfLines={1}>
          {name(team)}
        </Text>
        <Text style={styles.legScore}>{score(s1)}</Text>
        <Text style={styles.legScore}>{score(s2)}</Text>
        <Text style={[styles.legScore, styles.agg, won && styles.winner]}>{bothPlayed ? agg : '–'}</Text>
      </View>
    );
  };

  return (
    <View style={{ padding: space.md, gap: 4 }}>
      <View style={styles.legRow}>
        <Text style={[styles.legTeam, styles.legHead]} />
        <Text style={[styles.legScore, styles.legHead]}>L1</Text>
        <Text style={[styles.legScore, styles.legHead]}>L2</Text>
        <Text style={[styles.legScore, styles.legHead]}>Agg</Text>
      </View>
      {row(a, leg1.home_score, leg2.away_score, aggA)}
      {row(b, leg1.away_score, leg2.home_score, aggB)}
      {bothPlayed && aggA === aggB && winner ? <Text style={styles.pens}>{name(winner)} won on penalties</Text> : null}
      <View style={styles.legButtons}>
        {tie.map((f) => {
          const onPress = onLeg(f);
          return onPress ? (
            <Pressable key={f.id} onPress={onPress} hitSlop={8}>
              <Text style={styles.legButton}>{f.home_score == null ? `Enter leg ${f.leg} ›` : `Edit leg ${f.leg}`}</Text>
            </Pressable>
          ) : null;
        })}
      </View>
    </View>
  );
}

export function BracketTab({ competition, teams, fixtures, readOnly }: TabProps) {
  const rounds = buildRounds(fixtures);
  if (rounds.length === 0) {
    const body =
      competition.format === 'group_knockout'
        ? 'The bracket is drawn once the group stage is finished.'
        : competition.format === 'league_phase'
          ? 'The knockout is drawn once the league phase is finished.'
          : readOnly
            ? undefined
            : 'Add teams, then generate fixtures from the Teams tab.';
    return <EmptyState title="No bracket yet" body={body} />;
  }

  const name = teamNamer(teams);
  const final = rounds[rounds.length - 1].ties[0];
  const champion = final ? tieWinner(final) : null;
  const height = rounds[0].ties.length * SLOT_HEIGHT;
  const onLeg = (f: Fixture) =>
    canEnterResult(competition, fixtures, f, readOnly) ? () => openResult(competition.id, f.id) : undefined;

  return (
    <View style={{ gap: space.md }}>
      {champion && (
        <Card style={styles.champion}>
          <Text style={styles.championLabel}>Champion</Text>
          <Text style={styles.championName}>🏆 {name(champion)}</Text>
        </Card>
      )}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.md }}>
        {rounds.map((round, r) => (
          <View key={r} style={{ width: COLUMN_WIDTH }}>
            <Text style={styles.roundTitle}>{round.label}</Text>
            <View style={{ height, justifyContent: 'space-around' }}>
              {round.ties.map((tie, i) => (
                <Card key={tie?.[0].id ?? `tbd-${i}`} style={styles.match}>
                  {!tie ? (
                    <Text style={styles.tbd}>To be decided</Text>
                  ) : tie.length === 2 ? (
                    <TwoLegCard tie={tie} name={name} onLeg={onLeg} />
                  ) : (
                    <FixtureRow fixture={tie[0]} name={name} onPress={onLeg(tie[0])} />
                  )}
                </Card>
              ))}
            </View>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  roundTitle: { fontSize: 13, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: space.sm },
  match: { padding: 0, overflow: 'hidden' },
  tbd: { color: colors.muted, fontStyle: 'italic', padding: space.lg, textAlign: 'center' },
  champion: { backgroundColor: colors.ink, borderColor: colors.ink, alignItems: 'center', gap: space.xs },
  championLabel: { color: colors.accent, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 },
  championName: { color: '#FFFFFF', fontSize: 22, fontWeight: '800' },
  legRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  legTeam: { flex: 1, fontSize: 15, color: colors.ink },
  legHead: { fontSize: 11, color: colors.muted, fontWeight: '700' },
  legScore: { width: 28, textAlign: 'center', fontSize: 15, color: colors.ink, fontVariant: ['tabular-nums'] },
  agg: { fontWeight: '800' },
  winner: { fontWeight: '800', color: colors.winner },
  pens: { fontSize: 12, color: colors.muted, fontStyle: 'italic' },
  legButtons: { flexDirection: 'row', gap: space.lg, marginTop: 2 },
  legButton: { fontSize: 13, fontWeight: '600', color: colors.primary },
});
