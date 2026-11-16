import { Stack, useLocalSearchParams } from 'expo-router';
import { useRef, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, type TextInputInstance, View } from 'react-native';

import { api } from '@/api/client';
import type { Player } from '@/api/types';
import { Button, Card, colors, EmptyState, ErrorBanner, Loading, space } from '@/components/ui';
import { useAuth } from '@/lib/auth';
import { confirm, showError } from '@/lib/dialogs';
import { useLoad } from '@/lib/useLoad';

async function loadSquad(id: string, teamId: string) {
  const [competition, teams, players] = await Promise.all([
    api.getCompetition(id),
    api.listTeams(id),
    api.listPlayers(id, teamId),
  ]);
  return { competition, team: teams.find((t) => t.id === teamId) ?? null, players };
}

/** Digits only, 0–999; empty means "no number". */
function parseNumber(text: string): number | null {
  const digits = text.replace(/\D/g, '').slice(0, 3);
  return digits ? Number.parseInt(digits, 10) : null;
}

function NumberInput({ value, onChange, onSubmit }: { value: string; onChange: (v: string) => void; onSubmit?: () => void }) {
  return (
    <TextInput
      value={value}
      onChangeText={(t) => onChange(t.replace(/\D/g, '').slice(0, 3))}
      placeholder="#"
      placeholderTextColor={colors.muted}
      keyboardType="number-pad"
      maxLength={3}
      style={[styles.input, styles.numberInput]}
      onSubmitEditing={onSubmit}
      accessibilityLabel="Shirt number"
    />
  );
}

function PlayerRow({
  player, editable, onSave, onRemove,
}: {
  player: Player;
  editable: boolean;
  onSave: (changes: { name: string; shirt_number: number | null }) => Promise<boolean>;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(player.name);
  const [number, setNumber] = useState(player.shirt_number?.toString() ?? '');
  const [busy, setBusy] = useState(false);

  if (!editing) {
    return (
      <Pressable
        onPress={() => editable && setEditing(true)}
        disabled={!editable}
        style={styles.player}
        accessibilityRole={editable ? 'button' : undefined}
        accessibilityHint={editable ? 'Edit player' : undefined}
      >
        <Text style={styles.shirt}>{player.shirt_number ?? '–'}</Text>
        <Text style={styles.playerName}>{player.name}</Text>
        {editable && <Text style={styles.edit}>Edit</Text>}
      </Pressable>
    );
  }

  async function save() {
    if (!name.trim()) return;
    setBusy(true);
    const saved = await onSave({ name: name.trim(), shirt_number: parseNumber(number) });
    setBusy(false);
    if (saved) setEditing(false);
  }

  return (
    <View style={{ gap: space.sm, paddingVertical: space.md }}>
      <View style={styles.addRow}>
        <NumberInput value={number} onChange={setNumber} />
        <TextInput
          value={name}
          onChangeText={setName}
          maxLength={100}
          autoFocus
          style={[styles.input, { flex: 1 }]}
          onSubmitEditing={save}
          returnKeyType="done"
          accessibilityLabel="Player name"
        />
      </View>
      <View style={styles.addRow}>
        <Button title="Remove" variant="danger" onPress={onRemove} style={{ flex: 1 }} />
        <Button
          title="Cancel"
          variant="secondary"
          onPress={() => {
            setName(player.name);
            setNumber(player.shirt_number?.toString() ?? '');
            setEditing(false);
          }}
          style={{ flex: 1 }}
        />
        <Button title="Save" onPress={save} loading={busy} disabled={!name.trim()} style={{ flex: 1 }} />
      </View>
    </View>
  );
}

export default function SquadScreen() {
  const { id, teamId } = useLocalSearchParams<{ id: string; teamId: string }>();
  const { user } = useAuth();
  const { data, error, refreshing, reload, loading } = useLoad(() => loadSquad(id, teamId));
  const [name, setName] = useState('');
  const [number, setNumber] = useState('');
  const [adding, setAdding] = useState(false);
  const nameRef = useRef<TextInputInstance>(null);

  if (loading) return <Loading />;
  if (!data?.team) {
    return (
      <View style={{ padding: space.lg }}>
        <ErrorBanner message={error ?? 'Team not found'} />
      </View>
    );
  }

  const { competition, team, players } = data;
  const editable = competition.owner_id === user?.id && competition.status !== 'cancelled';

  async function add() {
    if (!name.trim()) return;
    setAdding(true);
    try {
      await api.addPlayer(id, teamId, { name: name.trim(), shirt_number: parseNumber(number) });
      setName('');
      // Suggest the next number, for quickly typing in a whole squad
      setNumber((n) => (n ? String(Math.min(999, Number(n) + 1)) : ''));
      await reload();
      nameRef.current?.focus();
    } catch (e) {
      showError(e);
    } finally {
      setAdding(false);
    }
  }

  async function save(player: Player, changes: { name: string; shirt_number: number | null }) {
    try {
      await api.updatePlayer(id, teamId, player.id, changes);
      await reload();
      return true;
    } catch (e) {
      showError(e);
      return false;
    }
  }

  async function remove(player: Player) {
    if (!(await confirm('Remove player?', `Remove ${player.name} from ${team!.name}?`, 'Remove', true))) return;
    try {
      await api.removePlayer(id, teamId, player.id);
      await reload();
    } catch (e) {
      showError(e);
    }
  }

  return (
    <ScrollView
      contentContainerStyle={{ padding: space.lg, gap: space.md, paddingBottom: 48 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={reload} />}
      keyboardShouldPersistTaps="handled"
    >
      <Stack.Screen options={{ title: team.name }} />
      <ErrorBanner message={error} />
      <Text style={styles.count}>
        {players.length} {players.length === 1 ? 'player' : 'players'}
      </Text>

      {editable && (
        <View style={styles.addRow}>
          <NumberInput value={number} onChange={setNumber} onSubmit={() => nameRef.current?.focus()} />
          <TextInput
            ref={nameRef}
            value={name}
            onChangeText={setName}
            placeholder="Player name"
            placeholderTextColor={colors.muted}
            maxLength={100}
            style={[styles.input, { flex: 1 }]}
            onSubmitEditing={add}
            submitBehavior="submit"
            returnKeyType="next"
            accessibilityLabel="New player name"
          />
          <Button title="Add" onPress={add} loading={adding} disabled={!name.trim()} />
        </View>
      )}

      {players.length === 0 ? (
        <EmptyState
          title="No players yet"
          body={editable ? 'Add the squad so you can record who scored, assisted and was booked.' : undefined}
        />
      ) : (
        <Card style={{ paddingVertical: space.xs }}>
          {players.map((p, i) => (
            <View key={p.id} style={i > 0 && styles.divider}>
              <PlayerRow player={p} editable={editable} onSave={(c) => save(p, c)} onRemove={() => remove(p)} />
            </View>
          ))}
        </Card>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  count: { color: colors.muted, fontSize: 14, fontWeight: '600' },
  addRow: { flexDirection: 'row', gap: space.sm, alignItems: 'center' },
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
  numberInput: { width: 64, textAlign: 'center' },
  player: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.md, minHeight: 48 },
  shirt: { width: 32, textAlign: 'center', fontWeight: '800', color: colors.primary, fontVariant: ['tabular-nums'] },
  playerName: { flex: 1, fontSize: 16, color: colors.ink },
  edit: { color: colors.primary, fontWeight: '600' },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
});
