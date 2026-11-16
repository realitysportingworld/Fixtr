// Mirrors the backend's Pydantic response schemas (backend/app/schemas)

export type CompetitionFormat = 'league' | 'knockout' | 'group_knockout' | 'league_phase';
export type SportType = 'football' | 'basketball' | 'rugby' | 'golf' | 'volleyball' | 'custom';
export type CompetitionStatus = 'draft' | 'active' | 'completed' | 'cancelled';
export type FixtureStatus = 'scheduled' | 'in_progress' | 'completed' | 'postponed';

export interface ScoringConfig {
  win: number;
  draw: number;
  loss: number;
  score_label?: string;
  lower_wins?: boolean;
  ranking?: 'points' | 'win_pct'; // win_pct = NBA-style table
  allow_draws?: boolean;
  // How teams level on points (or win %) are split; default score_difference
  tiebreak?: 'score_difference' | 'head_to_head';
  preset?: string | null;
}

export interface ScoringPreset {
  key: string;
  label: string;
  description: string;
  config: ScoringConfig;
}

export interface FormatConfig {
  // Knockout ties over two legs; for a league, everyone plays everyone home and away
  two_legged?: boolean;
  // league_phase only
  matches_per_team?: number;
  direct_qualifiers?: number;
  playoff_qualifiers?: number;
}

export interface User {
  id: string;
  email: string;
  username: string;
  is_premium: boolean;
}

export interface Competition {
  id: string;
  name: string;
  description: string | null;
  format: CompetitionFormat;
  sport: SportType;
  status: CompetitionStatus;
  max_participants: number;
  num_groups: number | null;
  scoring_config: ScoringConfig | null;
  format_config: FormatConfig | null;
  is_public: boolean;
  owner_id: string;
  owner_username: string | null;
  share_url: string | null; // owner only: the web page link, when sharing is on
  created_at: string;
}

export interface Team {
  id: string;
  name: string;
  competition_id: string;
  group_id: string | null;
}

export interface Fixture {
  id: string;
  competition_id: string;
  group_id: string | null;
  home_team_id: string;
  away_team_id: string | null; // null = BYE
  round_number: number;
  scheduled_at: string | null;
  status: FixtureStatus;
  knockout_round: string | null;
  bracket_position: number | null;
  leg: 1 | 2 | null; // two-legged knockout ties; null = single match
  is_bye: boolean;
  home_score: number | null;
  away_score: number | null;
  winner_id: string | null; // set by the backend, incl. aggregate and tiebreak wins
}

export interface Player {
  id: string;
  team_id: string;
  name: string;
  shirt_number: number | null;
}

export type MatchEventType = 'goal' | 'own_goal' | 'yellow_card' | 'red_card';

export interface MatchEventInput {
  type: MatchEventType;
  player_id: string;
  assist_player_id?: string | null; // goals only, a team-mate
  minute?: number | null;
}

export interface MatchEvent extends MatchEventInput {
  id: string;
  fixture_id: string;
  assist_player_id: string | null;
  minute: number | null;
}

export interface PlayerStatRow {
  rank: number; // shared on a tie
  player_id: string;
  player_name: string;
  shirt_number: number | null;
  team_id: string;
  team_name: string;
  value: number;
}

export interface DisciplineRow extends PlayerStatRow {
  yellow_cards: number;
  red_cards: number;
}

export interface CompetitionStats {
  supported: boolean; // player stats are kept for this sport
  scorers: PlayerStatRow[];
  assists: PlayerStatRow[];
  discipline: DisciplineRow[];
}

export interface StandingRow {
  team_id: string;
  team_name: string;
  played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
  win_pct: number;
  games_behind: number;
}

export interface Group {
  id: string;
  name: string;
  standings: StandingRow[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}
