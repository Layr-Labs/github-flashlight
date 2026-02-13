import React, { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import './Header.css';

function Header({ onSearchToggle }) {
  const location = useLocation();

  const isActive = (path) => {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  };

  // Global keyboard shortcut for search (Cmd+K or Ctrl+K)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        onSearchToggle();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onSearchToggle]);

  return (
    <header className="header">
      <div className="header-content">
        <Link to="/" className="logo">
          <h1>📊 Code Explorer</h1>
        </Link>
        <nav className="nav">
          <Link to="/" className={isActive('/') && !isActive('/components') ? 'nav-link active' : 'nav-link'}>
            🏠 Home
          </Link>
          <Link to="/components" className={isActive('/components') ? 'nav-link active' : 'nav-link'}>
            🔍 Components
          </Link>
          <button className="search-toggle-btn" onClick={onSearchToggle} title="Search (⌘K)">
            <span className="search-icon">🔍</span>
            <span className="search-text">Search</span>
            <kbd className="search-kbd">⌘K</kbd>
          </button>
        </nav>
      </div>
    </header>
  );
}

export default Header;
