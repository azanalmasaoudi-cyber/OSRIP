import { Component, type ErrorInfo, type ReactNode } from 'react';

import { reportClientError } from '@/api/monitoring';

/** Keeps a failing page from blanking the whole application; the error is reported. */
export class ErrorBoundary extends Component<{ fallback: (reset: () => void) => ReactNode; children: ReactNode; resetKey?: string }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    reportClientError(error.name, `${error.message} ${info.componentStack?.split('\n')[1]?.trim() ?? ''}`);
  }

  componentDidUpdate(previous: { resetKey?: string }): void {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) this.setState({ failed: false });
  }

  render(): ReactNode {
    return this.state.failed ? this.props.fallback(() => this.setState({ failed: false })) : this.props.children;
  }
}
