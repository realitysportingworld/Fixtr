import RNDateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import { useCallback, useState } from 'react';
import { Modal, Platform, StyleSheet, View } from 'react-native';

import { Button, colors, space } from '@/components/ui';

/** The next full hour: a sensible starting point when a match has no date yet. */
function nextHour(): Date {
  const d = new Date();
  d.setHours(d.getHours() + 1, 0, 0, 0);
  return d;
}

interface Pending {
  value: Date;
  resolve: (date: Date | null) => void;
}

/**
 * Pick a date and time. `pick()` resolves with the chosen moment, or null if
 * cancelled. Android uses the system date then time dialogs; iOS shows an
 * inline picker in a sheet, so render `picker` somewhere in the screen.
 */
export function useDateTimePicker() {
  const [pending, setPending] = useState<Pending | null>(null);

  const pick = useCallback((initial?: Date | null): Promise<Date | null> => {
    const start = initial ?? nextHour();
    if (Platform.OS === 'android') {
      return new Promise((resolve) => {
        DateTimePickerAndroid.open({
          value: start,
          mode: 'date',
          onChange: (event, date) => {
            if (event.type !== 'set' || !date) return resolve(null);
            DateTimePickerAndroid.open({
              value: date,
              mode: 'time',
              is24Hour: true,
              onChange: (e, time) => {
                if (e.type !== 'set' || !time) return resolve(null);
                const chosen = new Date(date);
                chosen.setHours(time.getHours(), time.getMinutes(), 0, 0);
                resolve(chosen);
              },
            });
          },
        });
      });
    }
    return new Promise((resolve) => setPending({ value: start, resolve }));
  }, []);

  const finish = (date: Date | null) => {
    pending?.resolve(date);
    setPending(null);
  };

  const picker = pending ? (
    <Modal transparent animationType="slide" onRequestClose={() => finish(null)}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <RNDateTimePicker
            value={pending.value}
            mode="datetime"
            display="inline"
            onChange={(_, date) => date && setPending({ ...pending, value: date })}
          />
          <View style={styles.actions}>
            <Button title="Cancel" variant="ghost" onPress={() => finish(null)} style={{ flex: 1 }} />
            <Button title="Done" onPress={() => finish(pending.value)} style={{ flex: 1 }} />
          </View>
        </View>
      </View>
    </Modal>
  ) : null;

  return { pick, picker };
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.35)' },
  sheet: { backgroundColor: colors.surface, padding: space.lg, paddingBottom: space.xl, gap: space.md, borderTopLeftRadius: 20, borderTopRightRadius: 20 },
  actions: { flexDirection: 'row', gap: space.sm },
});
