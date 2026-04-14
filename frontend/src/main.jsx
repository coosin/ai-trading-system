import React from 'react'
import ReactDOM from 'react-dom/client'
import './styles.css'

import App from './App.jsx'

class RootErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, errorText: '' };
  }

  static getDerivedStateFromError(error) {
    const msg = String(error?.message || error || '未知渲染错误');
    const stack = error?.stack ? `\n\n${String(error.stack)}` : '';
    return { hasError: true, errorText: `${msg}${stack}` };
  }

  componentDidCatch(error) {
    // Ensure we have something in both UI and browser console.
    // eslint-disable-next-line no-console
    console.error('RootErrorBoundary caught:', error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 20, fontFamily: 'monospace' }}>
          <div style={{ fontWeight: 800, marginBottom: 8 }}>前端渲染失败（已捕获错误）</div>
          <div style={{ color: '#dc2626', whiteSpace: 'pre-wrap' }}>{this.state.errorText}</div>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </React.StrictMode>,
)