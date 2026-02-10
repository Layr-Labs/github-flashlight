import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import './Header.css';

function Header() {
  const location = useLocation();

  const isActive = (path) => {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  };

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
        </nav>
      </div>
    </header>
  );
}

export default Header;
