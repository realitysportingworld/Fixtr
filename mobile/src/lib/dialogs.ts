import { Alert } from 'react-native';

import { errorText } from '@/lib/useLoad';

export function confirm(title: string, message: string, action: string, destructive = false): Promise<boolean> {
  return new Promise((resolve) => {
    Alert.alert(title, message, [
      { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
      { text: action, style: destructive ? 'destructive' : 'default', onPress: () => resolve(true) },
    ], { cancelable: true, onDismiss: () => resolve(false) });
  });
}

export function showError(e: unknown) {
  Alert.alert('Something went wrong', errorText(e));
}
