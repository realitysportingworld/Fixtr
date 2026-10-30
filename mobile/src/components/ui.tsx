import { ReactNode } from 'react';
import {
  ActivityIndicator, Pressable, StyleProp, StyleSheet, Text, TextInput, TextInputProps, View, ViewStyle,
} from 'react-native';

import type { CompetitionStatus } from '@/api/types';
import { STATUS_LABELS } from '@/lib/format';

export const colors = {
  bg: '#F3F5F2',
  surface: '#FFFFFF',
  ink: '#0E1B14',
  muted: '#5B6B62',
  border: '#DCE3DE',
  primary: '#0B6E4F', // pitch green
  primaryInk: '#FFFFFF',
  accent: '#D8F45B', // scoreboard lime
  danger: '#C2362B',
  dangerBg: '#FBE9E7',
  winner: '#0B6E4F',
};

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';

export function Button({
  title, onPress, variant = 'primary', loading, disabled, style,
}: {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const inactive = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={inactive}
      style={({ pressed }) => [
        styles.button,
        styles[`button_${variant}`],
        pressed && { opacity: 0.8 },
        inactive && { opacity: 0.5 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? colors.primaryInk : colors.primary} />
      ) : (
        <Text style={[styles.buttonText, styles[`buttonText_${variant}`]]}>{title}</Text>
      )}
    </Pressable>
  );
}

export function Field({ label, hint, ...props }: TextInputProps & { label: string; hint?: string }) {
  return (
    <View style={{ gap: space.xs }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput placeholderTextColor={colors.muted} style={styles.input} {...props} />
      {hint ? <Text style={styles.hint}>{hint}</Text> : null}
    </View>
  );
}

/** Pick one value from a short list, e.g. sport or format. */
export function OptionPicker<T extends string>({
  label, options, value, onChange,
}: {
  label?: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <View style={{ gap: space.xs }}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <View style={styles.chips}>
        {options.map((o) => {
          const selected = o.value === value;
          return (
            <Pressable
              key={o.value}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              onPress={() => onChange(o.value)}
              style={[styles.chip, selected && styles.chipSelected]}
            >
              <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{o.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <View style={styles.error}>
      <Text style={styles.errorText}>{message}</Text>
    </View>
  );
}

export function EmptyState({ title, body }: { title: string; body?: string }) {
  return (
    <View style={styles.empty}>
      <Text style={styles.emptyTitle}>{title}</Text>
      {body ? <Text style={styles.emptyBody}>{body}</Text> : null}
    </View>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

const STATUS_COLORS: Record<CompetitionStatus, [string, string]> = {
  draft: ['#ECEFED', '#4A5A51'],
  active: [colors.accent, colors.ink],
  completed: ['#DCEFE6', colors.primary],
  cancelled: [colors.dangerBg, colors.danger],
};

export function StatusBadge({ status }: { status: CompetitionStatus }) {
  const [bg, fg] = STATUS_COLORS[status];
  return (
    <View style={[styles.badge, { backgroundColor: bg }]}>
      <Text style={[styles.badgeText, { color: fg }]}>{STATUS_LABELS[status]}</Text>
    </View>
  );
}

export function Loading() {
  return (
    <View style={styles.empty}>
      <ActivityIndicator color={colors.primary} size="large" />
    </View>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 48,
    borderRadius: 12,
    paddingHorizontal: space.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  button_primary: { backgroundColor: colors.primary },
  button_secondary: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  button_danger: { backgroundColor: colors.dangerBg },
  button_ghost: { backgroundColor: 'transparent' },
  buttonText: { fontSize: 16, fontWeight: '600' },
  buttonText_primary: { color: colors.primaryInk },
  buttonText_secondary: { color: colors.ink },
  buttonText_danger: { color: colors.danger },
  buttonText_ghost: { color: colors.primary },
  label: { fontSize: 13, fontWeight: '600', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.5 },
  hint: { fontSize: 12, color: colors.muted },
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
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipSelected: { backgroundColor: colors.ink, borderColor: colors.ink },
  chipText: { fontSize: 14, color: colors.ink },
  chipTextSelected: { color: colors.accent, fontWeight: '600' },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: space.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  error: { backgroundColor: colors.dangerBg, borderRadius: 12, padding: space.md },
  errorText: { color: colors.danger, fontSize: 14 },
  empty: { alignItems: 'center', justifyContent: 'center', paddingVertical: 48, gap: space.sm },
  emptyTitle: { fontSize: 17, fontWeight: '600', color: colors.ink },
  emptyBody: { fontSize: 14, color: colors.muted, textAlign: 'center', paddingHorizontal: space.xl },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.muted,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginTop: space.md,
  },
  badge: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3, alignSelf: 'flex-start' },
  badgeText: { fontSize: 12, fontWeight: '700' },
});
