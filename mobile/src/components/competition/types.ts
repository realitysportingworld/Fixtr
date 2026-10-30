import type { Competition, Fixture, Group, StandingRow, Team } from '@/api/types';

export interface CompetitionData {
  competition: Competition;
  teams: Team[];
  fixtures: Fixture[];
  standings: StandingRow[]; // league and league_phase
  groups: Group[]; // group_knockout only
  readOnly: boolean; // viewing someone else's public competition
}

export type TabProps = CompetitionData & { reload: () => Promise<void> };

export function teamNamer(teams: Team[]) {
  const names = new Map(teams.map((t) => [t.id, t.name]));
  return (id: string | null) => (id ? (names.get(id) ?? 'Unknown') : 'BYE');
}
