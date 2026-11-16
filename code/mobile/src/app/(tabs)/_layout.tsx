// Modern layout: custom top NavBar + page content via Slot.
// Replaces the previous Expo Tabs-based side/bottom navigation.
import { Slot } from 'expo-router';
import React from 'react';
import { View } from 'react-native';
import { NavBar } from '../../components/NavBar';
import { colors } from '../../components/theme';

export default function TabsLayout() {
  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <NavBar />
      <View style={{ flex: 1 }}>
        <Slot />
      </View>
    </View>
  );
}
