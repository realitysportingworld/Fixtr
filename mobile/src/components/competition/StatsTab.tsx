import { StyleSheet, Text, View } from 'react-native';

import type { PlayerStatRow } from '@/api/types';
import { Card, colors, EmptyState, SectionTitle, space } from '@/components/ui';

import type { TabProps } from './types';

function Board({
  rows, unit, detail, spoken,
}: {
  rows: PlayerStatRow[];
  unit: string;
  detail?: (r: PlayerStatRow) => string; // shown instead of the number
  spoken?: (r: PlayerStatRow) => string; // what a screen reader says for it
}) {
  return (
    <Card style={{ paddingVertical: space.xs }}>
      {rows.map((r, i) => (
        <View key={r.player_id} style={[styles.row, i > 0 && styles.divider]}>
          <Text style={[styles.rank, r.rank === 1 && styles.leader]}>{r.rank}</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.name} numberOfLines={1}>
              {r.player_name}
            </Text>
            <Text style={styles.team} numberOfLines={1}>
              {r.team_name}
            </Text>
          </View>
          <Text style={styles.value} accessibilityLabel={spoken ? spoken(r) : `${r.value} ${unit}`}>
            {detail ? detail(r) : r.value}
          </Text>
        </View>
      ))}
    </Card>
  );
}

export function StatsTab({ stats, readOnly }: TabProps) {
  const cards = new Map(stats?.discipline.map((d) => [d.player_id, d]));
  if (!stats || (!stats.scorers.length && !stats.assists.length && !stats.discipline.length)) {
    return (
      <EmptyState
        title="No player stats yet"
        body={
          readOnly
            ? 'Scorers, assists and cards appear here once the organiser records them.'
            : 'Add players to each squad (Teams tab), then record who scored and was booked when you enter a result.'
        }
      />
    );
  }
  return (
    <View style={{ gap: space.md }}>
      {stats.scorers.length > 0 && (
        <>
          <SectionTitle>Top scorers</SectionTitle>
          <Board rows={stats.scorers} unit="goals" />
        </>
      )}
      {stats.assists.length > 0 && (
        <>
          <SectionTitle>Most assists</SectionTitle>
          <Board rows={stats.assists} unit="assists" />
        </>
      )}
      {stats.discipline.length > 0 && (
        <>
          <SectionTitle>Discipline</SectionTitle>
          <Board
            rows={stats.discipline}
            unit="cards"
            detail={(r) => {
              const d = cards.get(r.player_id)!;
              return [d.yellow_cards ? `🟨 ${d.yellow_cards}` : '', d.red_cards ? `🟥 ${d.red_cards}` : '']
                .filter(Boolean)
                .join('  ');
            }}
            spoken={(r) => {
              const d = cards.get(r.player_id)!;
              return `${d.yellow_cards} yellow, ${d.red_cards} red`;
            }}
          />
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: space.sm, minHeight: 52 },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  rank: { width: 24, textAlign: 'right', color: colors.muted, fontWeight: '700', fontVariant: ['tabular-nums'] },
  leader: { color: colors.primary },
  name: { fontSize: 16, fontWeight: '600', color: colors.ink },
  team: { fontSize: 13, color: colors.muted },
  value: { fontSize: 18, fontWeight: '800', color: colors.ink, fontVariant: ['tabular-nums'] },
});
