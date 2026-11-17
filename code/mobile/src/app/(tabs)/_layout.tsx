// Every top-level screen sits inside the application shell (sidebar + top bar).
import { Slot } from 'expo-router';
import React from 'react';
import { AppShell } from '../../components/NavBar';

export default function TabsLayout() {
  return (
    <AppShell>
      <Slot />
    </AppShell>
  );
}
