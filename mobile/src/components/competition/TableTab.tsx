import { ScrollView, StyleSheet, Text, View } from 'react-native';

import type { Competition, StandingRow } from '@/api/types';
import { Card, colors, EmptyState, SectionTitle, space } from '@/components/ui';
import { drawsAllowed, tiebreakText } from '@/lib/format';

import type { TabProps } from './types';

interface Column {
  label: string;
  value: (r: StandingRow) => string | number;
  bold?: boolean;
}

const POINTS_COLUMNS: Column[] = [
  { label: 'P', value: (r) => r.played },
  { label: 'Pts', value: (r) => r.points, bold: true }, // next to P so it's visible without scrolling
  { label: 'W', value: (r) => r.wins },
  { label: 'D', value: (r) => r.draws },
  { label: 'L', value: (r) => r.losses },
  { label: 'F', value: (r) => r.goals_for },
  { label: 'A', value: (r) => r.goals_against },
  { label: '+/-', value: (r) => r.goal_difference },
];

// NBA style: ranked by win percentage, games behind the leader instead of points
const WIN_PCT_COLUMNS: Column[] = [
  { label: 'W', value: (r) => r.wins },
  { label: 'L', value: (r) => r.losses },
  { label: 'PCT', value: (r) => r.win_pct.toFixed(3).replace(/^0/, ''), bold: true },
  { label: 'GB', value: (r) => (r.games_behind === 0 ? '–' : r.games_behind) },
  { label: 'PF', value: (r) => r.goals_for },
  { label: 'PA', value: (r) => r.goals_against },
  { label: '+/-', value: (r) => r.goal_difference },
];

function columnsFor(competition: Competition, rows: StandingRow[]): Column[] {
  if (competition.scoring_config?.ranking === 'win_pct') return WIN_PCT_COLUMNS;
  const showDraws = drawsAllowed(competition) || rows.some((r) => r.draws > 0);
  return POINTS_COLUMNS.filter((c) => c.label !== 'D' || showDraws);
}

interface Zone {
  upTo: number; // rows before this index are in the zone
  color: string;
  label: string;
}

/** Rows arrive already ranked by the backend. */
function StandingsTable({ rows, columns, zones = [] }: { rows: StandingRow[]; columns: Column[]; zones?: Zone[] }) {
  const zoneFor = (i: number) => zones.find((z) => i < z.upTo);
  return (
    <View style={{ gap: space.sm }}>
      <Card style={{ padding: 0, overflow: 'hidden' }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={{ minWidth: '100%' }}>
            <View style={[styles.row, styles.headerRow]}>
              <Text style={[styles.pos, styles.headText]}>#</Text>
              <Text style={[styles.team, styles.headText]}>Team</Text>
              {columns.map((c) => (
                <Text key={c.label} style={[styles.num, styles.headText, c.bold && styles.bold]}>
                  {c.label}
                </Text>
              ))}
            </View>
            {rows.map((r, i) => (
              <View key={r.team_id} style={[styles.row, i > 0 && styles.divider]}>
                <View style={[styles.zoneBar, { backgroundColor: zoneFor(i)?.color ?? 'transparent' }]} />
                <Text style={styles.pos}>{i + 1}</Text>
                <Text style={styles.team} numberOfLines={1}>
                  {r.team_name}
                </Text>
                {columns.map((c) => (
                  <Text key={c.label} style={[styles.num, c.bold && styles.bold]}>
                    {c.value(r)}
                  </Text>
                ))}
              </View>
            ))}
          </View>
        </ScrollView>
      </Card>
      {zones.length > 0 && (
        <View style={styles.legend}>
          {zones.map((z) => (
            <View key={z.label} style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: z.color }]} />
              <Text style={styles.legendText}>{z.label}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

function leaguePhaseZones(competition: Competition): Zone[] {
  const { direct_qualifiers: direct = 0, playoff_qualifiers: playoff = 0 } = competition.format_config ?? {};
  const zones: Zone[] = [];
  if (direct > 0) zones.push({ upTo: direct, color: colors.primary, label: 'Knockout' });
  if (playoff > 0) zones.push({ upTo: direct + playoff, color: '#E3B505', label: 'Play-off' });
  return zones;
}

export function TableTab({ competition, standings, groups, fixtures }: TabProps) {
  if (competition.format === 'group_knockout') {
    if (groups.length === 0) {
      return <EmptyState title="No groups yet" body="Groups are drawn when fixtures are generated." />;
    }
    const knockoutStarted = fixtures.some((f) => f.knockout_round);
    return (
      <View style={{ gap: space.sm }}>
        {knockoutStarted && <Text style={styles.note}>Group stage finished — see the Bracket tab.</Text>}
        {groups.map((g) => (
          <View key={g.id} style={{ gap: space.sm }}>
            <SectionTitle>{g.name}</SectionTitle>
            <StandingsTable rows={g.standings} columns={columnsFor(competition, g.standings)} />
          </View>
        ))}
        <Text style={styles.note}>{tiebreakText(competition)}</Text>
      </View>
    );
  }

  if (standings.length === 0) {
    return <EmptyState title="No table yet" body="The table fills in as results are entered." />;
  }
  const zones =
    competition.format === 'league_phase'
      ? leaguePhaseZones(competition)
      : competition.status === 'completed'
        ? [{ upTo: 1, color: colors.accent, label: 'Champion' }]
        : [];
  return (
    <View style={{ gap: space.sm }}>
      <StandingsTable rows={standings} columns={columnsFor(competition, standings)} zones={zones} />
      <Text style={styles.note}>{tiebreakText(competition)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: space.md, paddingVertical: space.md },
  headerRow: { backgroundColor: colors.ink },
  headText: { color: colors.accent, fontWeight: '700', fontSize: 12 },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  zoneBar: { position: 'absolute', left: 0, top: 0, bottom: 0, width: 4 },
  pos: { width: 24, color: colors.muted, fontSize: 14, fontVariant: ['tabular-nums'] },
  team: { width: 130, fontSize: 15, color: colors.ink, fontWeight: '600' },
  num: { width: 40, textAlign: 'center', fontSize: 14, color: colors.ink, fontVariant: ['tabular-nums'] },
  bold: { fontWeight: '800' },
  note: { color: colors.muted, fontSize: 14 },
  legend: { flexDirection: 'row', gap: space.lg, paddingHorizontal: space.xs },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { fontSize: 13, color: colors.muted },
});
