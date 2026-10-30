import * as SecureStore from 'expo-secure-store';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { api, setAuthToken, setUnauthorizedHandler } from '@/api/client';
import type { User } from '@/api/types';

const TOKEN_KEY = 'compapp.token';

interface AuthState {
  user: User | null;
  loading: boolean; // true while restoring a saved session at launch
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const signOut = useCallback(async () => {
    setAuthToken(null);
    setUser(null);
    await SecureStore.deleteItemAsync(TOKEN_KEY);
  }, []);

  const startSession = useCallback(async (token: string) => {
    setAuthToken(token);
    setUser(await api.me());
    await SecureStore.setItemAsync(TOKEN_KEY, token);
  }, []);

  // Restore the saved token on launch; an expired one just lands on login
  useEffect(() => {
    setUnauthorizedHandler(() => void signOut());
    (async () => {
      try {
        const token = await SecureStore.getItemAsync(TOKEN_KEY);
        if (token) await startSession(token);
      } catch {
        await signOut();
      } finally {
        setLoading(false);
      }
    })();
    return () => setUnauthorizedHandler(null);
  }, [signOut, startSession]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      signIn: async (email, password) => startSession((await api.login(email, password)).access_token),
      signUp: async (email, username, password) =>
        startSession((await api.register(email, username, password)).access_token),
      signOut,
    }),
    [user, loading, signOut, startSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
