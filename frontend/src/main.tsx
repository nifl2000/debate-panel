import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; error: string }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: '' };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, textAlign: 'center', fontFamily: 'system-ui', maxWidth: 600, margin: '0 auto' }}>
          <h2>⚠️ An error occurred</h2>
          <p style={{ color: '#666', fontSize: 14 }}>{this.state.error}</p>
          <button onClick={() => window.location.reload()} style={{ padding: '10px 20px', cursor: 'pointer', background: '#2563eb', color: '#fff', border: 'none', borderRadius: 8 }}>
            Seite neu laden
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)