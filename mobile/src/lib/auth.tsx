import * as SecureStore from 'expo-secure-store';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import {
  api, resumeSession, setTokens, setTokensRefreshedHandler, setUnauthorizedHandler, type Tokens, tokensFrom,
} from '@/api/client';
import type { TokenResponse, User } from '@/api/types';

const TOKENS_KEY = 'compapp.session';
const LEGACY_TOKEN_KEY = 'compapp.token'; // single 24-hour token, before refresh tokens

interface AuthState {
  user: User | null;
  loading: boolean; // true while restoring a saved session at launch
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, username: string, password: string) => Promise<void>;
  /** Sign in with the tokens from a password reset. */
  signInWith: (response: TokenResponse) => Promise<void>;
  signOut: () => Promise<void>;
  /** Forget this device's session without telling the server (it's already gone). */
  forget: () => Promise<void>;
  setUser: (user: User) => void;
}

const AuthContext = createContext<AuthState | null>(null);

async function saveTokens(tokens: Tokens) {
  await SecureStore.setItemAsync(TOKENS_KEY, JSON.stringify(tokens));
}

async function loadTokens(): Promise<Tokens | null> {
  const raw = await SecureStore.getItemAsync(TOKENS_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Tokens;
    return parsed.access && parsed.refresh ? parsed : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const forget = useCallback(async () => {
    setTokens(null);
    setUser(null);
    await SecureStore.deleteItemAsync(TOKENS_KEY);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout(); // ends the session on the server too
    } catch {
      // offline or already gone: the local sign-out below still happens
    }
    await forget();
  }, [forget]);

  const startSession = useCallback(async (response: TokenResponse) => {
    const tokens = tokensFrom(response);
    setTokens(tokens);
    await saveTokens(tokens);
    setUser(await api.me());
  }, []);

  // Restore the saved session on launch
  useEffect(() => {
    setUnauthorizedHandler(() => void forget());
    setTokensRefreshedHandler((tokens) => void saveTokens(tokens));
    (async () => {
      try {
        await SecureStore.deleteItemAsync(LEGACY_TOKEN_KEY);
        const saved = await loadTokens();
        if (saved) {
          const renewal = await resumeSession(saved);
          if (renewal === 'ended') await forget();
          else if (renewal === 'renewed') setUser(await api.me());
          // 'offline': stay on the sign-in screen without discarding the saved session
        }
      } catch {
        // can't reach the server right now; the saved session is kept for next launch
      } finally {
        setLoading(false);
      }
    })();
    return () => {
      setUnauthorizedHandler(null);
      setTokensRefreshedHandler(null);
    };
  }, [forget]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      signIn: async (email, password) => startSession(await api.login(email, password)),
      signUp: async (email, username, password) => startSession(await api.register(email, username, password)),
      signInWith: startSession,
      signOut,
      forget,
      setUser,
    }),
    [user, loading, signOut, forget, startSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
