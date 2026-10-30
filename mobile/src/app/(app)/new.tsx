import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { CompetitionFormat, ScoringConfig, SportType } from '@/api/types';
import { ScoringEditor, useDefaultScoring } from '@/components/ScoringEditor';
import { Button, Card, colors, ErrorBanner, Field, OptionPicker, SectionTitle, space } from '@/components/ui';
import { FORMAT_LABELS, SPORT_LABELS } from '@/lib/format';
import { errorText } from '@/lib/useLoad';

const FREE_TIER_LIMIT = 32; // backend/app/schemas/competition.py
const FALLBACK_SCORING: ScoringConfig = { win: 3, draw: 1, loss: 0 };

const FORMAT_HINTS: Record<CompetitionFormat, string> = {
  league: 'Everyone plays everyone, once or home and away. Top of the table wins.',
  knockout: 'Single elimination bracket. Lose and you are out.',
  group_knockout: 'Round-robin groups, then the top teams of each group go into a knockout.',
  league_phase:
    'One table, but each team plays only a set number of opponents. The top teams go straight to the ' +
    'knockout, the next ones play a play-off for the remaining places, and the rest are out.',
};

// Mirrors default_settings in backend/app/services/league_phase.py
function leaguePhaseDefaults(teams: number) {
  const bracket = teams >= 24 ? 16 : teams >= 12 ? 8 : teams >= 6 ? 4 : 2;
  let direct = bracket / 2;
  let playoff = bracket;
  if (direct + playoff > teams) [direct, playoff] = [2, 0];
  let matches = Math.min(8, teams - 1);
  if (teams % 2 && matches % 2) matches -= 1;
  return { matches: String(matches), direct: String(direct), playoff: String(playoff) };
}

const toOptions = <T extends string>(labels: Record<T, string>) =>
  (Object.keys(labels) as T[]).map((value) => ({ value, label: labels[value] }));

const int = (s: string) => Number.parseInt(s, 10) || 0;

function Toggle({ label, hint, value, onChange }: { label: string; hint: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View style={styles.toggle}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.toggleLabel}>{label}</Text>
        <Text style={styles.hint}>{hint}</Text>
      </View>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: colors.primary }} />
    </View>
  );
}

export default function NewCompetition() {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [format, setFormat] = useState<CompetitionFormat>('league');
  const [sport, setSport] = useState<SportType>('football');
  const [teams, setTeams] = useState('8');
  const [groups, setGroups] = useState('2');
  const [phase, setPhase] = useState(leaguePhaseDefaults(8));
  const [phaseEdited, setPhaseEdited] = useState(false);
  const [twoLegged, setTwoLegged] = useState(false);
  const [isPublic, setIsPublic] = useState(false);
  const defaultScoring = useDefaultScoring(sport);
  const [scoring, setScoring] = useState<ScoringConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // A new sport starts from that sport's default rules
  useEffect(() => setScoring(defaultScoring), [defaultScoring]);

  // Keep league phase numbers in proportion to the team count until edited
  useEffect(() => {
    if (!phaseEdited && int(teams) >= 2) setPhase(leaguePhaseDefaults(int(teams)));
  }, [teams, phaseEdited]);

  const editPhase = (key: keyof typeof phase) => (v: string) => {
    setPhaseEdited(true);
    setPhase((p) => ({ ...p, [key]: v }));
  };

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const competition = await api.createCompetition({
        name: name.trim(),
        description: description.trim() || null,
        format,
        sport,
        max_participants: int(teams),
        num_groups: format === 'group_knockout' ? int(groups) : null,
        scoring_config: scoring,
        format_config:
          format === 'league_phase'
            ? {
                two_legged: twoLegged,
                matches_per_team: int(phase.matches),
                direct_qualifiers: int(phase.direct),
                playoff_qualifiers: int(phase.playoff),
              }
            : { two_legged: twoLegged },
        is_public: isPublic,
      });
      router.dismiss();
      router.push({ pathname: '/competition/[id]', params: { id: competition.id } });
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  const direct = int(phase.direct);
  const playoff = int(phase.playoff);

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={{ padding: space.lg, gap: space.lg }} keyboardShouldPersistTaps="handled">
        <ErrorBanner message={error} />
        <Field label="Name" value={name} onChangeText={setName} placeholder="Sunday League" maxLength={100} />
        <Field
          label="Description (optional)"
          value={description}
          onChangeText={setDescription}
          maxLength={1000}
          multiline
        />
        <OptionPicker label="Sport" options={toOptions(SPORT_LABELS)} value={sport} onChange={setSport} />
        <OptionPicker label="Format" options={toOptions(FORMAT_LABELS)} value={format} onChange={setFormat} />
        <Text style={styles.hint}>{FORMAT_HINTS[format]}</Text>
        <Field
          label="Max teams"
          value={teams}
          onChangeText={setTeams}
          keyboardType="number-pad"
          hint={`Free accounts can have up to ${FREE_TIER_LIMIT} teams.`}
        />
        {format === 'group_knockout' && (
          <Field
            label="Number of groups"
            value={groups}
            onChangeText={setGroups}
            keyboardType="number-pad"
            hint="At least 2 groups, with at least 2 teams in each."
          />
        )}

        {format === 'league_phase' && (
          <>
            <SectionTitle>League phase</SectionTitle>
            <Card style={{ gap: space.md }}>
              <Field
                label="Matches per team"
                value={phase.matches}
                onChangeText={editPhase('matches')}
                keyboardType="number-pad"
                hint="Each against a different opponent (the Champions League uses 8)."
              />
              <View style={{ flexDirection: 'row', gap: space.sm }}>
                <View style={{ flex: 1 }}>
                  <Field label="Straight through" value={phase.direct} onChangeText={editPhase('direct')} keyboardType="number-pad" />
                </View>
                <View style={{ flex: 1 }}>
                  <Field label="Play-off places" value={phase.playoff} onChangeText={editPhase('playoff')} keyboardType="number-pad" />
                </View>
              </View>
              <Text style={styles.hint}>
                {playoff > 0
                  ? `Top ${direct} qualify directly; ${direct + 1}–${direct + playoff} play off for ${playoff / 2} more places` +
                    ` (${direct + playoff / 2}-team knockout). The rest are eliminated.`
                  : `Top ${direct} go into the knockout; the rest are eliminated.`}
              </Text>
            </Card>
          </>
        )}

        {format === 'league' ? (
          <Toggle
            label="Home and away"
            hint="Everyone plays everyone twice, once at each ground."
            value={twoLegged}
            onChange={setTwoLegged}
          />
        ) : (
          <Toggle
            label="Two-legged ties"
            hint="Knockout ties are played home and away, decided on aggregate. The final is one match."
            value={twoLegged}
            onChange={setTwoLegged}
          />
        )}

        <SectionTitle>Scoring</SectionTitle>
        <ScoringEditor sport={sport} value={scoring ?? FALLBACK_SCORING} onChange={setScoring} />

        <Toggle
          label="Public"
          hint="Anyone can find this competition in search and follow it. Only you can change it."
          value={isPublic}
          onChange={setIsPublic}
        />

        <Button title="Create competition" onPress={create} loading={busy} disabled={!name.trim()} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  hint: { fontSize: 13, color: colors.muted },
  toggle: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  toggleLabel: { fontSize: 16, fontWeight: '600', color: colors.ink },
});
