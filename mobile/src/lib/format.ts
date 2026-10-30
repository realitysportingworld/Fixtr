import type { Competition, CompetitionFormat, CompetitionStatus, Fixture, SportType } from '@/api/types';

export const FORMAT_LABELS: Record<CompetitionFormat, string> = {
  league: 'League',
  knockout: 'Knockout',
  group_knockout: 'Groups + Knockout',
  league_phase: 'Champions League style',
};

export const SPORT_LABELS: Record<SportType, string> = {
  football: 'Football',
  basketball: 'Basketball',
  rugby: 'Rugby',
  golf: 'Golf',
  volleyball: 'Volleyball',
  custom: 'Custom',
};

export const STATUS_LABELS: Record<CompetitionStatus, string> = {
  draft: 'Draft',
  active: 'Active',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

/** Formats whose table stage (groups / league phase) is followed by a knockout. */
export const hasStageThenKnockout = (c: Competition) => c.format === 'group_knockout' || c.format === 'league_phase';

/** Team that went through: the BYE's team, or the winner the backend recorded. */
export function fixtureWinner(f: Fixture): string | null {
  return f.is_bye ? f.home_team_id : f.winner_id;
}

export function lowerWins(c: Competition): boolean {
  return c.scoring_config?.lower_wins ?? c.sport === 'golf';
}

export function drawsAllowed(c: Competition): boolean {
  return c.scoring_config?.allow_draws ?? true;
}

/** "Sat 7 Nov · 15:00" in the phone's own time zone and language. */
export function formatKickoff(iso: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  return `${day} · ${time}`;
}

/** How teams level on points are separated, as one readable line. */
export function tiebreakText(c: Competition): string {
  const label = (c.scoring_config?.score_label ?? 'Score').toLowerCase().replace(/s$/, '');
  const difference = `${label} difference, ${label}s scored`;
  return c.scoring_config?.tiebreak === 'head_to_head'
    ? `Level teams: head-to-head, then ${difference}.`
    : `Level teams: ${difference}, then head-to-head.`;
}
