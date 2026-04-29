import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Surface the crash in the dev console so desktop users can share logs.
    // eslint-disable-next-line no-console
    console.error("Aegis 2 render error:", error, info);
    this.setState({ info });
  }

  reset = () => {
    this.setState({ error: null, info: null });
  };

  render() {
    if (this.state.error) {
      return (
        <div className="card" style={{ margin: 24 }}>
          <h1>Something went wrong.</h1>
          <p className="hero-sub">
            Aegis 2 caught a rendering error. Your data is safe. You can try to
            recover, or reload the app.
          </p>
          <pre className="error" style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>
            {String(this.state.error?.stack || this.state.error)}
          </pre>
          <div className="row" style={{ marginTop: 12, gap: 8 }}>
            <button className="btn primary" onClick={this.reset}>
              Try again
            </button>
            <button
              className="btn"
              onClick={() => {
                window.location.hash = "#/";
                window.location.reload();
              }}
            >
              Reload home
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
