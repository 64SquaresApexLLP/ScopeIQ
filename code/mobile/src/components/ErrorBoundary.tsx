import React from 'react';
import { View } from 'react-native';
import { getLogger } from '../lib/logger';
import { Body, Button, Title } from './ui';

const log = getLogger('ui');

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    log.error(`render error: ${error.message}`, { stack: String(info.componentStack).slice(0, 1500) });
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <View style={{ padding: 24, gap: 12 }}>
        <Title>Something went wrong on this screen</Title>
        <Body>{this.state.error.message}</Body>
        <Button title="Try again" onPress={() => this.setState({ error: null })} />
      </View>
    );
  }
}
