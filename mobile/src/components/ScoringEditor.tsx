import { useEffect, useState } from 'react';
import { StyleSheet, Switch, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { ScoringConfig, ScoringPreset, SportType } from '@/api/types';
import { Card, colors, Field, OptionPicker, space } from '@/components/ui';

const CUSTOM = 'custom';

let presetCache: Promise<Record<SportType, ScoringPreset[]>> | null = null;
function loadPresets() {
  presetCache ??= api.scoringPresets().catch((e) => {
    presetCache = null; // retry next time
    throw e;
  });
  return presetCache;
}

/**
 * Every rule spelled out, so saving over an existing config (PATCH merges)
 * can't leave e.g. NBA's win-percentage ranking behind after switching to FIBA.
 */
export function completeConfig(config: ScoringConfig): ScoringConfig {
  return {
    ...config,
    lower_wins: config.lower_wins ?? false,
    allow_draws: config.allow_draws ?? true,
    ranking: config.ranking ?? 'points',
    tiebreak: config.tiebreak ?? 'score_difference',
    preset: config.preset ?? CUSTOM,
  };
}

const fromPreset = (p: ScoringPreset) => completeConfig({ ...p.config, preset: p.key });

/** Default scoring for a sport (its first preset), once presets have loaded. */
export function useDefaultScoring(sport: SportType): ScoringConfig | null {
  const [config, setConfig] = useState<ScoringConfig | null>(null);
  useEffect(() => {
    let live = true;
    loadPresets()
      .then((p) => live && setConfig(fromPreset(p[sport][0])))
      .catch(() => live && setConfig(null));
    return () => {
      live = false;
    };
  }, [sport]);
  return config;
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <View style={styles.toggle}>
      <Text style={styles.toggleLabel}>{label}</Text>
      <Switch value={value} onValueChange={onChange} trackColor={{ true: colors.primary }} />
    </View>
  );
}

export function ScoringEditor({
  sport, value, onChange,
}: {
  sport: SportType;
  value: ScoringConfig;
  onChange: (config: ScoringConfig) => void;
}) {
  const [presets, setPresets] = useState<ScoringPreset[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    let live = true;
    loadPresets()
      .then((all) => live && setPresets(all[sport] ?? []))
      .catch(() => live && setError(true));
    return () => {
      live = false;
    };
  }, [sport]);

  const selected = presets.some((p) => p.key === value.preset) ? value.preset! : CUSTOM;
  const preset = presets.find((p) => p.key === selected);
  const options = [...presets.map((p) => ({ value: p.key, label: p.label })), { value: CUSTOM, label: 'Custom' }];

  function choose(key: string) {
    const chosen = presets.find((p) => p.key === key);
    onChange(chosen ? fromPreset(chosen) : completeConfig({ ...value, preset: CUSTOM }));
  }

  // Any manual edit turns the rules into a custom set
  const edit = (patch: Partial<ScoringConfig>) => onChange(completeConfig({ ...value, ...patch, preset: CUSTOM }));
  const setPoints = (key: 'win' | 'draw' | 'loss') => (text: string) =>
    edit({ [key]: Number.parseInt(text.replace(/\D/g, ''), 10) || 0 });

  const winPct = value.ranking === 'win_pct';
  const differenceLabel = `${(value.score_label ?? 'score').toLowerCase().replace(/s$/, '')} difference`;

  return (
    <Card style={{ gap: space.md }}>
      {error ? <Text style={styles.muted}>Couldn't load scoring presets — you can still set custom rules.</Text> : null}
      <OptionPicker options={options} value={selected} onChange={choose} />
      {preset?.description ? <Text style={styles.muted}>{preset.description}</Text> : null}

      {selected === CUSTOM && (
        <View style={{ gap: space.md }}>
          {!winPct && (
            <View style={{ flexDirection: 'row', gap: space.sm }}>
              {(['win', 'draw', 'loss'] as const).map((key) => (
                <View key={key} style={{ flex: 1 }}>
                  <Field
                    label={key}
                    value={String(value[key])}
                    onChangeText={setPoints(key)}
                    keyboardType="number-pad"
                  />
                </View>
              ))}
            </View>
          )}
          <Toggle label="Rank by win percentage (no points)" value={winPct} onChange={(v) => edit({ ranking: v ? 'win_pct' : 'points' })} />
          <Toggle
            label={`Head-to-head before ${differenceLabel}`}
            value={value.tiebreak === 'head_to_head'}
            onChange={(v) => edit({ tiebreak: v ? 'head_to_head' : 'score_difference' })}
          />
          <Toggle label="Allow draws" value={value.allow_draws ?? true} onChange={(allow_draws) => edit({ allow_draws })} />
          <Toggle label="Lowest score wins (e.g. golf strokes)" value={value.lower_wins ?? false} onChange={(lower_wins) => edit({ lower_wins })} />
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  muted: { fontSize: 14, color: colors.muted },
  toggle: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  toggleLabel: { fontSize: 15, color: colors.ink, flex: 1 },
});
