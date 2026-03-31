import React from 'react';
import { useSystemStore } from '../store';

function ThemeToggle() {
  const { theme, toggleTheme } = useSystemStore();

  return (
    <button
      onClick={toggleTheme}
      style={{
        padding: '8px 16px',
        backgroundColor: theme === 'dark' ? '#34495e' : '#f8f9fa',
        color: theme === 'dark' ? 'white' : '#343a40',
        border: `1px solid ${theme === 'dark' ? '#5a6d80' : '#ced4da'}`,
        borderRadius: '20px',
        cursor: 'pointer',
        fontSize: '14px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px'
      }}
    >
      {theme === 'dark' ? (
        <>
          <span>☀️</span>
          <span>切换到浅色模式</span>
        </>
      ) : (
        <>
          <span>🌙</span>
          <span>切换到深色模式</span>
        </>
      )}
    </button>
  );
}

export default ThemeToggle;