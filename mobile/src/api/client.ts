import Constants from 'expo-constants';

import type {
  Competition, CompetitionFormat, CompetitionStats, CompetitionStatus, Fixture, FormatConfig, Group,
  MatchEvent, MatchEventInput, Player, ScoringConfig, ScoringPreset, SportType, StandingRow, Team,
  TokenResponse, User,
} from './types';

/**
 * Backend base URL. EXPO_PUBLIC_API_URL wins; otherwise use the dev machine's
 * IP (the host Expo Go loaded the bundle from) so a phone on the same Wi-Fi
 * reaches the API without any config.
 */
function resolveBaseUrl(): string {
  const explicit = process.env.EXPO_PUBLIC_API_URL;
  if (explicit) return explicit.replace(/\/+$/, '');
  const port = process.env.EXPO_PUBLIC_API_PORT || '8000';
  const host = Constants.expoConfig?.hostUri?.split(':')[0] ?? 'localhost';
  return `http://${host}:${port}/api/v1`;
}

export const API_URL = resolveBaseUrl();

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

let authToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}

/** Called when an authenticated request gets a 401 (expired or revoked token). */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

/** Turn FastAPI's error body into one readable sentence. */
function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    // 422 validation errors: [{loc: ['body', 'password'], msg: '...'}]
    return detail
      .map((e: { loc?: (string | number)[]; msg?: string }) => {
        const field = e.loc?.filter((p) => p !== 'body').join('.');
        const msg = (e.msg ?? 'Invalid value').replace(/^Value error, /, '');
        return field ? `${field}: ${msg}` : msg;
      })
      .join('\n');
  }
  if (status === 429) return 'Too many attempts. Please wait and try again.';
  return `Request failed (${status})`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(`Can't reach the server at ${API_URL}`, 0);
  }

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && authToken) onUnauthorized?.();
    throw new ApiError(errorMessage(data, res.status), res.status);
  }
  return data as T;
}

const comp = (id: string) => `/competitions/${id}`;

export const api = {
  // Auth
  login: (email: string, password: string) =>
    request<TokenResponse>('POST', '/auth/login', { email, password }),
  register: (email: string, username: string, password: string) =>
    request<TokenResponse>('POST', '/auth/register', { email, username, password }),
  me: () => request<User>('GET', '/auth/me'),

  // Competitions
  listCompetitions: () => request<Competition[]>('GET', '/competitions/'),
  searchPublic: (q: string) => request<Competition[]>('GET', `/competitions/public?q=${encodeURIComponent(q)}`),
  scoringPresets: () => request<Record<SportType, ScoringPreset[]>>('GET', '/competitions/scoring-presets'),
  getCompetition: (id: string) => request<Competition>('GET', comp(id)),
  createCompetition: (payload: {
    name: string;
    description?: string | null;
    format: CompetitionFormat;
    sport: SportType;
    max_participants: number;
    num_groups?: number | null;
    scoring_config?: Partial<ScoringConfig> | null;
    format_config?: FormatConfig | null;
    is_public?: boolean;
  }) => request<Competition>('POST', '/competitions/', payload),
  updateCompetition: (
    id: string,
    payload: Partial<{
      name: string;
      description: string | null;
      status: CompetitionStatus;
      scoring_config: Partial<ScoringConfig>;
      is_public: boolean;
    }>,
  ) => request<Competition>('PATCH', comp(id), payload),
  deleteCompetition: (id: string) => request<void>('DELETE', comp(id)),
  // Web page link anyone can open; enabling again returns the same link
  enableShareLink: (id: string) => request<{ share_url: string }>('POST', `${comp(id)}/share`),
  // Kills the link for good; enabling afterwards makes a new one
  disableShareLink: (id: string) => request<void>('DELETE', `${comp(id)}/share`),

  // Teams
  listTeams: (id: string) => request<Team[]>('GET', `${comp(id)}/teams/`),
  addTeam: (id: string, name: string) => request<Team>('POST', `${comp(id)}/teams/`, { name }),
  fillTeams: (id: string) => request<Team[]>('POST', `${comp(id)}/teams/generate`),
  removeTeam: (id: string, teamId: string) => request<void>('DELETE', `${comp(id)}/teams/${teamId}`),

  // Squads
  listPlayers: (id: string, teamId: string) => request<Player[]>('GET', `${comp(id)}/teams/${teamId}/players/`),
  addPlayer: (id: string, teamId: string, player: { name: string; shirt_number: number | null }) =>
    request<Player>('POST', `${comp(id)}/teams/${teamId}/players/`, player),
  updatePlayer: (id: string, teamId: string, playerId: string, changes: { name?: string; shirt_number?: number | null }) =>
    request<Player>('PATCH', `${comp(id)}/teams/${teamId}/players/${playerId}`, changes),
  removePlayer: (id: string, teamId: string, playerId: string) =>
    request<void>('DELETE', `${comp(id)}/teams/${teamId}/players/${playerId}`),

  // Fixtures
  listFixtures: (id: string) => request<Fixture[]>('GET', `${comp(id)}/fixtures/`),
  generateFixtures: (id: string) => request<Fixture[]>('POST', `${comp(id)}/fixtures/generate`),
  regenerateFixtures: (id: string) => request<Fixture[]>('POST', `${comp(id)}/fixtures/regenerate`),
  // teams_per_group only matters for group knockout; league phase uses its format_config
  advanceToKnockout: (id: string, teamsPerGroup = 2) =>
    request<Fixture[]>('POST', `${comp(id)}/fixtures/advance-to-knockout`, { teams_per_group: teamsPerGroup }),
  // Set or clear (null) kick-off times, many fixtures at once
  scheduleFixtures: (id: string, items: { fixtureId: string; at: Date | null }[]) =>
    request<{ updated: number }>(
      'PATCH',
      `${comp(id)}/fixtures/schedule`,
      items.map((i) => ({ fixture_id: i.fixtureId, scheduled_at: i.at ? i.at.toISOString() : null })),
    ),

  // Results
  saveResult: (
    id: string,
    fixtureId: string,
    score: { home: number; away: number; tiebreakWinner?: 'home' | 'away' | null },
    isUpdate: boolean,
    // Replaces the match's scorers and cards; leave out to keep what's recorded
    events?: MatchEventInput[],
  ) =>
    request<unknown>(isUpdate ? 'PUT' : 'POST', `${comp(id)}/fixtures/${fixtureId}/result`, {
      home_score: score.home,
      away_score: score.away,
      tiebreak_winner: score.tiebreakWinner ?? null,
      ...(events ? { events } : {}),
    }),
  matchEvents: (id: string, fixtureId: string) => request<MatchEvent[]>('GET', `${comp(id)}/fixtures/${fixtureId}/events`),
  // Un-play a match: back to scheduled, tables and bracket updated
  clearResult: (id: string, fixtureId: string) => request<void>('DELETE', `${comp(id)}/fixtures/${fixtureId}/result`),

  // Tables
  standings: (id: string) => request<StandingRow[]>('GET', `${comp(id)}/standings/`),
  groups: (id: string) => request<Group[]>('GET', `${comp(id)}/groups/`),
  stats: (id: string) => request<CompetitionStats>('GET', `${comp(id)}/stats/`),
};
