import { router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Switch, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { Competition, CompetitionStatus, ScoringConfig } from '@/api/types';
import { completeConfig, ScoringEditor } from '@/components/ScoringEditor';
import { Button, Card, colors, SectionTitle, space } from '@/components/ui';
import { confirm, showError } from '@/lib/dialogs';
import { FORMAT_LABELS, lowerWins, STATUS_LABELS } from '@/lib/format';
import { shareCompetition } from '@/lib/share';

import type { TabProps } from './types';

/** Format choices are fixed once the competition exists; show what they are. */
function formatSummary(c: Competition): string[] {
  const lines = [FORMAT_LABELS[c.format]];
  const config = c.format_config ?? {};
  if (c.format === 'group_knockout') lines.push(`${c.num_groups} groups`);
  if (c.format === 'league_phase') {
    lines.push(`${config.matches_per_team} matches per team`);
    lines.push(`Top ${config.direct_qualifiers} straight to the knockout`);
    if (config.playoff_qualifiers) lines.push(`Next ${config.playoff_qualifiers} in the play-off`);
  }
  if (c.format === 'league') lines.push(config.two_legged ? 'Home and away: everyone plays twice' : 'Everyone plays once');
  else lines.push(config.two_legged ? 'Two-legged ties (single-match final)' : 'Single-match ties');
  return lines;
}

export function SettingsTab({ competition, fixtures, reload }: TabProps) {
  const [scoring, setScoring] = useState<ScoringConfig>(() =>
    completeConfig({
      win: 3,
      draw: 1,
      loss: 0,
      ...competition.scoring_config,
      lower_wins: lowerWins(competition),
    }),
  );
  const [busy, setBusy] = useState<string | null>(null);

  async function run(kind: string, fn: () => Promise<unknown>, after: () => unknown = reload) {
    setBusy(kind);
    try {
      await fn();
      await after();
    } catch (e) {
      showError(e);
    } finally {
      setBusy(null);
    }
  }

  // Mirrors the transitions allowed by PATCH /competitions/{id}
  const hasFixtures = fixtures.length > 0;
  const statuses: CompetitionStatus[] = (
    hasFixtures ? ['active', 'completed', 'cancelled'] : ['draft', 'cancelled']
  ).filter((s) => s !== competition.status) as CompetitionStatus[];

  async function setStatus(status: CompetitionStatus) {
    const destructive = status === 'cancelled';
    const ok = await confirm(
      `Mark as ${STATUS_LABELS[status].toLowerCase()}?`,
      destructive ? 'No more results can be entered while cancelled.' : '',
      STATUS_LABELS[status],
      destructive,
    );
    if (ok) await run(status, () => api.updateCompetition(competition.id, { status }));
  }

  const saveScoring = () => run('scoring', () => api.updateCompetition(competition.id, { scoring_config: scoring }));

  async function regenerate() {
    const ok = await confirm(
      'Regenerate fixtures?',
      'Every fixture and result will be deleted and a fresh draw made. This cannot be undone.',
      'Regenerate',
      true,
    );
    if (ok) await run('regenerate', () => api.regenerateFixtures(competition.id));
  }

  async function remove() {
    const ok = await confirm('Delete competition?', `"${competition.name}" and all its data will be deleted.`, 'Delete', true);
    if (ok) await run('delete', () => api.deleteCompetition(competition.id), () => router.back());
  }

  const canRegenerate = hasFixtures && competition.status === 'active';

  async function turnOffLink() {
    const ok = await confirm(
      'Turn off the link?',
      'Anyone you sent it to will no longer be able to open it. You can make a new link later.',
      'Turn off',
      true,
    );
    if (ok) await run('link-off', () => api.disableShareLink(competition.id));
  }

  async function newLink() {
    const ok = await confirm(
      'Make a new link?',
      'The current link stops working, so only people you send the new one to can open it.',
      'New link',
      true,
    );
    if (!ok) return;
    await run('link-new', async () => {
      await api.disableShareLink(competition.id);
      await api.enableShareLink(competition.id);
    });
  }

  return (
    <View style={{ gap: space.md }}>
      <SectionTitle>Visibility</SectionTitle>
      <Card style={styles.switchRow}>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={styles.label}>Public</Text>
          <Text style={styles.hint}>
            {competition.is_public
              ? 'Anyone can find this in search and view it. Only you can change it.'
              : 'Only you can see this competition.'}
          </Text>
        </View>
        <Switch
          value={competition.is_public}
          disabled={busy === 'public'}
          onValueChange={(is_public) => run('public', () => api.updateCompetition(competition.id, { is_public }))}
          trackColor={{ true: colors.primary }}
        />
      </Card>

      <SectionTitle>Share link</SectionTitle>
      <Card style={{ gap: space.sm }}>
        <Text style={styles.hint}>
          {competition.share_url
            ? 'Anyone with this link can see the table, fixtures, results and scorers in a web browser. No app or account needed.'
            : 'Make a link to a web page with the table, fixtures, results and scorers, for anyone to open. No app or account needed.'}
        </Text>
        {competition.share_url ? (
          <Text selectable style={styles.link} numberOfLines={2}>
            {competition.share_url}
          </Text>
        ) : null}
        <Button
          title={competition.share_url ? 'Share link' : 'Make a link and share it'}
          onPress={() => run('share', () => shareCompetition(competition))}
          loading={busy === 'share'}
          disabled={busy !== null}
        />
        {competition.share_url ? (
          <View style={{ flexDirection: 'row', gap: space.sm }}>
            <Button title="New link" variant="secondary" onPress={newLink} loading={busy === 'link-new'} disabled={busy !== null} style={{ flex: 1 }} />
            <Button title="Turn off" variant="danger" onPress={turnOffLink} loading={busy === 'link-off'} disabled={busy !== null} style={{ flex: 1 }} />
          </View>
        ) : null}
      </Card>

      <SectionTitle>Status</SectionTitle>
      <Card style={{ gap: space.sm }}>
        <Text style={styles.body}>
          Currently <Text style={{ fontWeight: '700' }}>{STATUS_LABELS[competition.status]}</Text>
        </Text>
        {statuses.map((s) => (
          <Button
            key={s}
            title={`Mark as ${STATUS_LABELS[s].toLowerCase()}`}
            variant={s === 'cancelled' ? 'danger' : 'secondary'}
            onPress={() => setStatus(s)}
            loading={busy === s}
          />
        ))}
      </Card>

      <SectionTitle>Scoring</SectionTitle>
      <ScoringEditor sport={competition.sport} value={scoring} onChange={setScoring} />
      <Text style={styles.hint}>Saving recalculates the table from the results entered so far.</Text>
      <Button title="Save scoring" onPress={saveScoring} loading={busy === 'scoring'} />

      <SectionTitle>Format</SectionTitle>
      <Card style={{ gap: 4 }}>
        {formatSummary(competition).map((line) => (
          <Text key={line} style={styles.body}>
            {line}
          </Text>
        ))}
      </Card>

      <SectionTitle>Danger zone</SectionTitle>
      <Card style={{ gap: space.sm }}>
        {canRegenerate && (
          <Button title="Regenerate fixtures" variant="danger" onPress={regenerate} loading={busy === 'regenerate'} />
        )}
        <Button title="Delete competition" variant="danger" onPress={remove} loading={busy === 'delete'} />
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  body: { fontSize: 15, color: colors.ink },
  label: { fontSize: 16, fontWeight: '600', color: colors.ink },
  hint: { fontSize: 13, color: colors.muted },
  switchRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  link: { fontSize: 14, color: colors.primary, fontWeight: '600' },
});
