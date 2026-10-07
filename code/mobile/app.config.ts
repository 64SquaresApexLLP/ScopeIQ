/// <reference types="node" />
// Environment selection happens outside the code: APP_ENV=dev|test|prod picks config/<env>.json, and
// SCOPEIQ_API_URL overrides the API address (e.g. your PC's LAN IP when testing on a phone with Expo Go).
import type { ConfigContext, ExpoConfig } from 'expo/config';
import fs from 'fs';
import path from 'path';

export default ({ config }: ConfigContext): ExpoConfig => {
  const env = (process.env.APP_ENV || 'dev').toLowerCase();
  const file = path.join(__dirname, 'config', `${env}.json`);
  if (!fs.existsSync(file)) throw new Error(`APP_ENV=${env}: ${file} not found (use dev, test or prod)`);
  const settings = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (process.env.SCOPEIQ_API_URL) settings.apiUrl = process.env.SCOPEIQ_API_URL;
  return { ...(config as ExpoConfig), name: env === 'prod' ? 'ScopeIQ' : `ScopeIQ (${env})`, extra: { ...config.extra, env, ...settings } };
};
