import { Platform, Share } from 'react-native';

import { api } from '@/api/client';
import type { Competition } from '@/api/types';

/**
 * Open the system share sheet (WhatsApp, Messages, copy...) with the
 * competition's web page link, turning link sharing on first if needed.
 * Resolves with the link.
 */
export async function shareCompetition(competition: Competition): Promise<string> {
  const url = competition.share_url ?? (await api.enableShareLink(competition.id)).share_url;
  const message = `${competition.name}: live table, fixtures and results`;
  // iOS attaches `url` as a link; Android only sends `message`, so it carries the link
  await Share.share(
    Platform.OS === 'ios' ? { message, url } : { message: `${message}\n${url}`, title: competition.name },
    { dialogTitle: `Share ${competition.name}`, subject: competition.name },
  );
  return url;
}
