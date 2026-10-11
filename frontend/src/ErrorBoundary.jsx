import { Component } from "react";

// Crash guard: if a panel throws while rendering, show a small message there
// instead of blanking the whole page.
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Panel crashed:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="m-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
        Something went wrong in this panel.{" "}
        <button className="underline" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}
