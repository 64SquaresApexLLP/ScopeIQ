import Constants from 'expo-constants';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';
export interface AppSettings {
  env: 'dev' | 'test' | 'prod';
  apiUrl: string;
  logLevel: LogLevel;
  remoteLogLevel: LogLevel;
  logNetwork: boolean;
  showEnvBanner: boolean;
}

const extra = (Constants.expoConfig?.extra ?? {}) as Partial<AppSettings>;

export const settings: AppSettings = {
  env: extra.env ?? 'dev',
  apiUrl: (extra.apiUrl ?? 'http://localhost:8000').replace(/\/$/, ''),
  logLevel: extra.logLevel ?? 'debug',
  remoteLogLevel: extra.remoteLogLevel ?? 'warn',
  logNetwork: extra.logNetwork ?? false,
  showEnvBanner: extra.showEnvBanner ?? true,
};
