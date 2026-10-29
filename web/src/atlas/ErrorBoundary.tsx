import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props { label: string; children: ReactNode; fallback?: ReactNode }
interface State { error: Error | null }

/** Contains a failure to one panel; the rest of the page keeps working. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[${this.props.label}]`, error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      this.props.fallback ?? (
        <div role="alert" className="p-4 text-sm text-muted">
          {this.props.label} could not be drawn: {this.state.error.message}
        </div>
      )
    );
  }
}
