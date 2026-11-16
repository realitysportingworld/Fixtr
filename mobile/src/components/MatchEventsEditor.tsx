import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { MatchEventInput, MatchEventType, Player } from '@/api/types';
import { Button, Card, colors, space } from '@/components/ui';

export type Side = 'home' | 'away';
export type DraftEvent = MatchEventInput & { key: string };
export type Squads = Record<Side, Player[]>;

const TYPE_LABELS: Record<MatchEventType, string> = {
  goal: 'Goal',
  own_goal: 'Own goal',
  yellow_card: 'Yellow card',
  red_card: 'Red card',
};
const TYPE_ICONS: Record<MatchEventType, string> = { goal: '⚽', own_goal: 'OG', yellow_card: '🟨', red_card: '🟥' };

let nextKey = 0;
export const draftKey = () => `e${nextKey++}`;

/** Goals each side is credited with: its own goals plus the other side's own goals. */
export function goalsBySide(events: MatchEventInput[], sideOf: (playerId: string) => Side | undefined): Record<Side, number> {
  const goals = { home: 0, away: 0 };
  for (const e of events) {
    const side = sideOf(e.player_id);
    if (!side) continue;
    if (e.type === 'goal') goals[side] += 1;
    if (e.type === 'own_goal') goals[side === 'home' ? 'away' : 'home'] += 1;
  }
  return goals;
}

function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextSelected]} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

const playerLabel = (p: Player) => (p.shirt_number != null ? `${p.shirt_number} ${p.name}` : p.name);

/** Pick type, team, player (and assist, minute) for one new event. */
function Composer({
  teams, squads, onAdd, onCancel, onCreatePlayer,
}: {
  teams: Record<Side, string>;
  squads: Squads;
  onAdd: (e: DraftEvent) => void;
  onCancel: () => void;
  onCreatePlayer: (side: Side, name: string) => Promise<Player | null>;
}) {
  const [type, setType] = useState<MatchEventType>('goal');
  const [side, setSide] = useState<Side>('home');
  const [playerId, setPlayerId] = useState<string | null>(null);
  const [assistId, setAssistId] = useState<string | null>(null);
  const [minute, setMinute] = useState('');
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  const squad = squads[side];
  const ownGoal = type === 'own_goal';

  function pickSide(s: Side) {
    setSide(s);
    setPlayerId(null);
    setAssistId(null);
  }

  async function create() {
    if (!newName.trim()) return;
    setCreating(true);
    const player = await onCreatePlayer(side, newName.trim());
    setCreating(false);
    if (player) {
      setNewName('');
      setPlayerId(player.id);
    }
  }

  function add() {
    if (!playerId) return;
    const m = Number.parseInt(minute, 10);
    onAdd({
      key: draftKey(),
      type,
      player_id: playerId,
      assist_player_id: type === 'goal' ? assistId : null,
      minute: Number.isFinite(m) && m >= 1 ? Math.min(m, 150) : null,
    });
  }

  return (
    <Card style={{ gap: space.md }}>
      <View style={styles.chips}>
        {(Object.keys(TYPE_LABELS) as MatchEventType[]).map((t) => (
          <Chip key={t} label={TYPE_LABELS[t]} selected={type === t} onPress={() => setType(t)} />
        ))}
      </View>

      <View style={{ gap: space.xs }}>
        <Text style={styles.label}>{ownGoal ? 'Scored into their own net' : 'Team'}</Text>
        <View style={styles.row}>
          {(['home', 'away'] as const).map((s) => (
            <Pressable
              key={s}
              onPress={() => pickSide(s)}
              accessibilityRole="radio"
              accessibilityState={{ selected: side === s }}
              style={[styles.sidePick, side === s && styles.chipSelected]}
            >
              <Text style={[styles.chipText, side === s && styles.chipTextSelected]} numberOfLines={1}>
                {teams[s]}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      <View style={{ gap: space.xs }}>
        <Text style={styles.label}>Player</Text>
        {squad.length === 0 && <Text style={styles.hint}>No squad yet. Add a player below.</Text>}
        <View style={styles.chips}>
          {squad.map((p) => (
            <Chip
              key={p.id}
              label={playerLabel(p)}
              selected={playerId === p.id}
              onPress={() => {
                setPlayerId(p.id);
                if (assistId === p.id) setAssistId(null);
              }}
            />
          ))}
        </View>
        <View style={styles.row}>
          <TextInput
            value={newName}
            onChangeText={setNewName}
            placeholder={`New ${teams[side]} player`}
            placeholderTextColor={colors.muted}
            maxLength={100}
            style={[styles.input, { flex: 1 }]}
            onSubmitEditing={create}
            accessibilityLabel={`New ${teams[side]} player name`}
          />
          <Button title="Add" variant="secondary" onPress={create} loading={creating} disabled={!newName.trim()} />
        </View>
      </View>

      {type === 'goal' && squad.length > 1 && (
        <View style={{ gap: space.xs }}>
          <Text style={styles.label}>Assist (optional)</Text>
          <View style={styles.chips}>
            <Chip label="None" selected={assistId === null} onPress={() => setAssistId(null)} />
            {squad
              .filter((p) => p.id !== playerId)
              .map((p) => (
                <Chip key={p.id} label={playerLabel(p)} selected={assistId === p.id} onPress={() => setAssistId(p.id)} />
              ))}
          </View>
        </View>
      )}

      <View style={[styles.row, { alignItems: 'center' }]}>
        <Text style={[styles.label, { flex: 1 }]}>Minute (optional)</Text>
        <TextInput
          value={minute}
          onChangeText={(t) => setMinute(t.replace(/\D/g, '').slice(0, 3))}
          placeholder="–"
          placeholderTextColor={colors.muted}
          keyboardType="number-pad"
          style={[styles.input, { width: 72, textAlign: 'center' }]}
          accessibilityLabel="Minute"
        />
      </View>

      <View style={styles.row}>
        <Button title="Cancel" variant="ghost" onPress={onCancel} style={{ flex: 1 }} />
        <Button title={`Add ${TYPE_LABELS[type].toLowerCase()}`} onPress={add} disabled={!playerId} style={{ flex: 2 }} />
      </View>
    </Card>
  );
}

/**
 * Scorers, assists and cards for one match. Edits stay local and are saved
 * with the result, so the score and its scorers always change together.
 */
export function MatchEventsEditor({
  teams, score, squads, events, onChange, onCreatePlayer, disabled,
}: {
  teams: Record<Side, string>;
  score: Record<Side, number>;
  squads: Squads;
  events: DraftEvent[];
  onChange: (events: DraftEvent[]) => void;
  onCreatePlayer: (side: Side, name: string) => Promise<Player | null>;
  disabled?: boolean;
}) {
  const [composing, setComposing] = useState(false);
  const players = new Map<string, { player: Player; side: Side }>();
  for (const side of ['home', 'away'] as const) for (const p of squads[side]) players.set(p.id, { player: p, side });
  const sideOf = (id: string) => players.get(id)?.side;
  const nameOf = (id: string | null | undefined) => (id ? (players.get(id)?.player.name ?? 'Unknown') : '');

  const goals = goalsBySide(events, sideOf);
  const sorted = [...events].sort((a, b) => (a.minute ?? 999) - (b.minute ?? 999));

  return (
    <View style={{ gap: space.sm }}>
      <View style={styles.header}>
        <Text style={styles.title}>Scorers and cards</Text>
        <Text style={styles.tally}>
          {(['home', 'away'] as const).map((s) => `${goals[s]}/${score[s]}`).join('  ·  ')} goals named
        </Text>
      </View>

      {sorted.length > 0 && (
        <Card style={{ paddingVertical: space.xs }}>
          {sorted.map((e, i) => {
            const side = sideOf(e.player_id);
            const team = side ? teams[side] : '';
            return (
              <View key={e.key} style={[styles.event, i > 0 && styles.divider]}>
                <Text style={styles.icon}>{TYPE_ICONS[e.type]}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={styles.eventText}>
                    {e.minute ? `${e.minute}'  ` : ''}
                    {nameOf(e.player_id)}
                    {e.type === 'own_goal' ? ' (own goal)' : ''}
                  </Text>
                  <Text style={styles.eventMeta}>
                    {team}
                    {e.assist_player_id ? ` · assist ${nameOf(e.assist_player_id)}` : ''}
                  </Text>
                </View>
                {!disabled && (
                  <Pressable
                    onPress={() => onChange(events.filter((x) => x.key !== e.key))}
                    hitSlop={12}
                    accessibilityLabel={`Remove ${TYPE_LABELS[e.type].toLowerCase()} by ${nameOf(e.player_id)}`}
                  >
                    <Text style={styles.remove}>Remove</Text>
                  </Pressable>
                )}
              </View>
            );
          })}
        </Card>
      )}

      {(goals.home > score.home || goals.away > score.away) && (
        <Text style={styles.warning}>More goals are named than the score allows. Remove some or change the score.</Text>
      )}

      {composing ? (
        <Composer
          teams={teams}
          squads={squads}
          onCreatePlayer={onCreatePlayer}
          onCancel={() => setComposing(false)}
          onAdd={(e) => {
            onChange([...events, e]);
            setComposing(false);
          }}
        />
      ) : (
        !disabled && <Button title="+ Add scorer or card" variant="secondary" onPress={() => setComposing(true)} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: space.sm },
  title: { fontSize: 13, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.8 },
  tally: { fontSize: 13, color: colors.muted, fontVariant: ['tabular-nums'] },
  label: { fontSize: 13, fontWeight: '600', color: colors.muted },
  hint: { fontSize: 13, color: colors.muted },
  warning: { fontSize: 14, color: colors.danger, textAlign: 'center' },
  row: { flexDirection: 'row', gap: space.sm },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    maxWidth: '100%',
  },
  sidePick: {
    flex: 1,
    minHeight: 44,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.sm,
  },
  chipSelected: { backgroundColor: colors.ink, borderColor: colors.ink },
  chipText: { fontSize: 14, color: colors.ink },
  chipTextSelected: { color: colors.accent, fontWeight: '600' },
  input: {
    minHeight: 44,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    paddingHorizontal: space.md,
    fontSize: 16,
    color: colors.ink,
  },
  event: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.sm, minHeight: 48 },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  icon: { width: 28, textAlign: 'center', fontSize: 16, fontWeight: '800', color: colors.danger },
  eventText: { fontSize: 15, color: colors.ink, fontWeight: '600' },
  eventMeta: { fontSize: 13, color: colors.muted },
  remove: { color: colors.danger, fontWeight: '600' },
});
