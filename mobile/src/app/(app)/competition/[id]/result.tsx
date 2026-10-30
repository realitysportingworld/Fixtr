import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { api } from '@/api/client';
import type { Fixture } from '@/api/types';
import { useDateTimePicker } from '@/components/DateTimePicker';
import { Button, Card, colors, ErrorBanner, Loading, space } from '@/components/ui';
import { confirm } from '@/lib/dialogs';
import { drawsAllowed, formatKickoff } from '@/lib/format';
import { errorText } from '@/lib/useLoad';

type Side = 'home' | 'away';

interface Match {
  fixture: Fixture;
  firstLeg: Fixture | null; // set when this is a second leg
  home: string;
  away: string;
  label: string;
  scoreLabel: string;
  drawsAllowed: boolean;
}

function ScoreInput({ team, value, onChange }: { team: string; value: number; onChange: (v: number) => void }) {
  return (
    <View style={styles.side}>
      <Text style={styles.team} numberOfLines={2}>
        {team}
      </Text>
      <View style={styles.stepper}>
        <Pressable
          onPress={() => onChange(Math.max(0, value - 1))}
          style={styles.step}
          accessibilityLabel={`Decrease ${team} score`}
        >
          <Text style={styles.stepText}>−</Text>
        </Pressable>
        <TextInput
          value={String(value)}
          onChangeText={(t) => onChange(Math.min(100_000, Number.parseInt(t.replace(/\D/g, ''), 10) || 0))}
          keyboardType="number-pad"
          selectTextOnFocus
          style={styles.score}
          accessibilityLabel={`${team} score`}
        />
        <Pressable onPress={() => onChange(value + 1)} style={styles.step} accessibilityLabel={`Increase ${team} score`}>
          <Text style={styles.stepText}>+</Text>
        </Pressable>
      </View>
    </View>
  );
}

function TiebreakPicker({ match, value, onChange }: { match: Match; value: Side | null; onChange: (s: Side) => void }) {
  return (
    <View style={{ gap: space.sm }}>
      <Text style={styles.question}>Level — who won on penalties / tiebreak?</Text>
      <View style={{ flexDirection: 'row', gap: space.sm }}>
        {(['home', 'away'] as const).map((side) => (
          <Pressable
            key={side}
            onPress={() => onChange(side)}
            accessibilityRole="radio"
            accessibilityState={{ selected: value === side }}
            style={[styles.pick, value === side && styles.pickSelected]}
          >
            <Text style={[styles.pickText, value === side && styles.pickTextSelected]} numberOfLines={1}>
              {side === 'home' ? match.home : match.away}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

export default function ResultScreen() {
  const { id, fixtureId } = useLocalSearchParams<{ id: string; fixtureId: string }>();
  const [match, setMatch] = useState<Match | null>(null);
  const [home, setHome] = useState(0);
  const [away, setAway] = useState(0);
  const [tiebreak, setTiebreak] = useState<Side | null>(null);
  const [kickoff, setKickoff] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<'save' | 'clear' | 'date' | null>(null);
  const { pick, picker } = useDateTimePicker();

  useEffect(() => {
    (async () => {
      try {
        const [competition, teams, fixtures] = await Promise.all([
          api.getCompetition(id),
          api.listTeams(id),
          api.listFixtures(id),
        ]);
        const f = fixtures.find((x) => x.id === fixtureId);
        if (!f) throw new Error('Fixture not found');
        const name = (tid: string | null) => teams.find((t) => t.id === tid)?.name ?? 'Unknown';
        const firstLeg =
          f.leg === 2
            ? (fixtures.find(
                (x) => x.leg === 1 && x.round_number === f.round_number && x.bracket_position === f.bracket_position,
              ) ?? null)
            : null;
        setMatch({
          fixture: f,
          firstLeg,
          home: name(f.home_team_id),
          away: name(f.away_team_id),
          label: [f.knockout_round ?? `Round ${f.round_number}`, f.leg ? `Leg ${f.leg}` : null].filter(Boolean).join(' · '),
          scoreLabel: competition.scoring_config?.score_label ?? 'Score',
          drawsAllowed: drawsAllowed(competition),
        });
        setKickoff(f.scheduled_at);
        setHome(f.home_score ?? 0);
        setAway(f.away_score ?? 0);
        if (f.winner_id) setTiebreak(f.winner_id === f.home_team_id ? 'home' : 'away');
      } catch (e) {
        setError(errorText(e));
      }
    })();
  }, [id, fixtureId]);

  if (!match) {
    return error ? (
      <View style={{ padding: space.lg }}>
        <ErrorBanner message={error} />
      </View>
    ) : (
      <Loading />
    );
  }

  const { fixture, firstLeg } = match;
  const knockout = fixture.knockout_round != null;
  // Second leg: this leg's home side was away in the first leg
  const aggregate = firstLeg
    ? { home: home + (firstLeg.away_score ?? 0), away: away + (firstLeg.home_score ?? 0) }
    : null;
  const decidesTie = knockout && fixture.leg !== 1;
  const level = aggregate ? aggregate.home === aggregate.away : home === away;
  const needsTiebreak = decidesTie && level;
  const drawBlocked = !knockout && !match.drawsAllowed && home === away;

  async function setDate(at: Date | null) {
    setBusy('date');
    setError(null);
    try {
      await api.scheduleFixtures(id, [{ fixtureId, at }]);
      setKickoff(at ? at.toISOString() : null);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  async function changeDate() {
    const at = await pick(kickoff ? new Date(kickoff) : null);
    if (at) await setDate(at);
  }

  async function clearResult() {
    const message =
      'The match goes back to unplayed and the table updates.' +
      (knockout ? ' If the winner was already drawn into the next round, that match is removed until this one is played again.' : '');
    if (!(await confirm('Clear this result?', message, 'Clear result', true))) return;
    setBusy('clear');
    setError(null);
    try {
      await api.clearResult(id, fixtureId);
      router.back();
    } catch (e) {
      setError(errorText(e));
      setBusy(null);
    }
  }

  async function save() {
    setBusy('save');
    setError(null);
    try {
      await api.saveResult(
        id,
        fixtureId,
        { home, away, tiebreakWinner: needsTiebreak ? tiebreak : null },
        played,
      );
      router.back();
    } catch (e) {
      setError(errorText(e));
      setBusy(null);
    }
  }

  const played = fixture.home_score != null;

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <Text style={styles.round}>{match.label}</Text>
      <Text style={styles.scoreLabel}>{match.scoreLabel}</Text>
      <Card style={styles.when}>
        <Text style={[styles.whenText, !kickoff && { color: colors.muted }]}>
          {kickoff ? formatKickoff(kickoff) : 'No date set'}
        </Text>
        {kickoff ? (
          <Pressable onPress={() => setDate(null)} disabled={busy !== null} hitSlop={8} accessibilityRole="button">
            <Text style={styles.whenLink}>Remove</Text>
          </Pressable>
        ) : null}
        <Pressable onPress={changeDate} disabled={busy !== null} hitSlop={8} accessibilityRole="button">
          <Text style={styles.whenLink}>{busy === 'date' ? 'Saving…' : kickoff ? 'Change' : 'Set date'}</Text>
        </Pressable>
      </Card>
      <View style={styles.board}>
        <ScoreInput team={match.home} value={home} onChange={setHome} />
        <Text style={styles.vs}>vs</Text>
        <ScoreInput team={match.away} value={away} onChange={setAway} />
      </View>
      {aggregate && (
        <Text style={styles.aggregate}>
          Aggregate {aggregate.home}–{aggregate.away}
          {'  '}(first leg {match.away} {firstLeg?.home_score}–{firstLeg?.away_score} {match.home})
        </Text>
      )}
      {fixture.leg === 1 && <Text style={styles.hint}>The second leg decides the tie on aggregate.</Text>}
      <Button
        title="Reset to 0–0"
        variant="ghost"
        onPress={() => {
          setHome(0);
          setAway(0);
          setTiebreak(null);
        }}
        disabled={home === 0 && away === 0 && tiebreak === null}
      />
      {needsTiebreak && <TiebreakPicker match={match} value={tiebreak} onChange={setTiebreak} />}
      {drawBlocked && <Text style={styles.hint}>Draws aren't allowed — enter the final score after overtime.</Text>}
      <ErrorBanner message={error} />
      <Button
        title={played ? 'Update result' : 'Save result'}
        onPress={save}
        loading={busy === 'save'}
        disabled={busy !== null || drawBlocked || (needsTiebreak && !tiebreak)}
      />
      {played && (
        <Button title="Clear result" variant="danger" onPress={clearResult} loading={busy === 'clear'} disabled={busy !== null} />
      )}
      {picker}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: space.lg, gap: space.lg },
  round: { textAlign: 'center', fontSize: 13, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', letterSpacing: 1 },
  scoreLabel: { textAlign: 'center', fontSize: 14, color: colors.muted, marginTop: -space.md },
  board: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.ink,
    borderRadius: 20,
    paddingVertical: space.xl,
    paddingHorizontal: space.md,
  },
  side: { flex: 1, alignItems: 'center', gap: space.md },
  team: { color: '#FFFFFF', fontSize: 16, fontWeight: '700', textAlign: 'center', minHeight: 40 },
  stepper: { alignItems: 'center', gap: space.sm },
  step: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(255,255,255,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepText: { color: colors.accent, fontSize: 24, fontWeight: '700' },
  score: {
    color: colors.accent,
    fontSize: 48,
    fontWeight: '900',
    textAlign: 'center',
    minWidth: 80,
    fontVariant: ['tabular-nums'],
  },
  vs: { color: 'rgba(255,255,255,0.5)', fontSize: 14, fontWeight: '700' },
  aggregate: { textAlign: 'center', fontSize: 15, fontWeight: '700', color: colors.ink },
  when: { flexDirection: 'row', alignItems: 'center', gap: space.lg, paddingVertical: space.md },
  whenText: { flex: 1, fontSize: 15, fontWeight: '600', color: colors.ink },
  whenLink: { color: colors.primary, fontWeight: '600', fontSize: 15 },
  hint: { color: colors.muted, textAlign: 'center', fontSize: 14 },
  question: { fontSize: 15, fontWeight: '600', color: colors.ink, textAlign: 'center' },
  pick: {
    flex: 1,
    minHeight: 48,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.sm,
  },
  pickSelected: { backgroundColor: colors.ink, borderColor: colors.ink },
  pickText: { fontSize: 15, fontWeight: '600', color: colors.ink },
  pickTextSelected: { color: colors.accent },
});
