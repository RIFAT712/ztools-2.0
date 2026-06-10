import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

export const Header: React.FC = () => {
  const [isLight, setIsLight] = useState(() => localStorage.getItem('theme') === 'light');

  useEffect(() => {
    if (isLight) {
      document.body.classList.add('light');
    } else {
      document.body.classList.remove('light');
    }
  }, [isLight]);

  const toggleTheme = () => {
    const next = !isLight;
    setIsLight(next);
    localStorage.setItem('theme', next ? 'light' : 'dark');
  };

  return (
    <div className="header">
      <div className="header-top">
        <Link to="/" style={{ textDecoration: 'none', color: 'inherit' }}>
          <h1 className="title">উইকি নিবন্ধের শব্দ গণক</h1>
        </Link>
        <div className="auth-box">
          <button id="themeToggle" title="থিম পরিবর্তন করুন" onClick={toggleTheme}>
            {isLight ? '🌙' : '☀️'}
          </button>
        </div>
      </div>
    </div>
  );
};
