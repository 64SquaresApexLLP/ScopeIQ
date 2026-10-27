// Sign-in: SCOPER uses a username + password the admin created; other roles still pick a demo account. Session persisted
// with AsyncStorage (works on web and native).
import AsyncStorage from '@react-native-async-storage/async-storage';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, setToken, setUnauthorizedHandler } from './api';
import { getLogger } from './logger';
import { User } from './types';

const KEY = 'scopeiq.session';
const log = getLogger('auth');

// Either a demo account ({ userId }) or a username + password created by the admin.
export type LoginCreds = { userId: string } | { username: string; password: string };

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (creds: LoginCreds) => Promise<void>;
  logout: () => Promise<void>;
  can: (...roles: string[]) => boolean;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const logout = useCallback(async () => {
    setToken(null);
    setUser(null);
    try {
      await AsyncStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      log.info('session expired');
      void logout();
    });
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(KEY);
        if (raw) {
          const s = JSON.parse(raw) as { token: string; user: User };
          setToken(s.token);
          setUser(s.user);
        }
      } catch (e) {
        log.warn('could not restore session', { error: String(e) });
      } finally {
        setReady(true);
      }
    })();
  }, [logout]);

  const login = useCallback(async (creds: LoginCreds) => {
    const body = 'username' in creds ? { username: creds.username.trim(), password: creds.password } : { user_id: creds.userId, password: 'demo' };
    const res = await api.post<{ token: string; user: User }>('/auth/login', body);
    setToken(res.token);
    setUser(res.user);
    log.info(`signed in as ${res.user.user_id} (${res.user.role})`);
    try {
      await AsyncStorage.setItem(KEY, JSON.stringify(res));
    } catch {
      /* session only lasts for this launch */
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, ready, login, logout, can: (...roles) => !!user && (user.role === 'ADMIN' || roles.includes(user.role)) }),
    [user, ready, login, logout],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const c = useContext(Ctx);
  if (!c) throw new Error('useAuth outside AuthProvider');
  return c;
}
