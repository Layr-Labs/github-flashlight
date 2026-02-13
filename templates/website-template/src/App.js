import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import LibraryGraph from './components/LibraryGraph';
import ApplicationGraph from './components/ApplicationGraph';
import ComponentDetails from './components/ComponentDetails';
import Dashboard from './components/Dashboard';
import './styles/App.css';

function App() {
  const [searchQuery, setSearchQuery] = useState('');
  const [currentView, setCurrentView] = useState('dashboard');

  return (
    <Router>
      <div className="App">
        <header className="app-header">
          <h1 className="app-title">EigenDA Spec</h1>
          <p className="app-subtitle">Codebase Explorer</p>

          <ul className="nav-menu">
            <li className="nav-item">
              <Link
                to="/"
                className={`nav-link ${currentView === 'dashboard' ? 'active' : ''}`}
                onClick={() => setCurrentView('dashboard')}
              >
                System Overview
              </Link>
            </li>
            <li className="nav-item">
              <Link
                to="/library-graph"
                className={`nav-link ${currentView === 'library' ? 'active' : ''}`}
                onClick={() => setCurrentView('library')}
              >
                Library Graph
              </Link>
            </li>
            <li className="nav-item">
              <Link
                to="/application-graph"
                className={`nav-link ${currentView === 'application' ? 'active' : ''}`}
                onClick={() => setCurrentView('application')}
              >
                Application Graph
              </Link>
            </li>
            <li className="nav-item">
              <Link
                to="/components"
                className={`nav-link ${currentView === 'components' ? 'active' : ''}`}
                onClick={() => setCurrentView('components')}
              >
                Components
              </Link>
            </li>
          </ul>

          <div className="search-container">
            <input
              type="text"
              placeholder="Search components..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="search-input"
            />
          </div>
        </header>

        <main className="app-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/library-graph" element={<LibraryGraph searchQuery={searchQuery} />} />
            <Route path="/application-graph" element={<ApplicationGraph searchQuery={searchQuery} />} />
            <Route path="/components" element={<ComponentDetails searchQuery={searchQuery} />} />
            <Route path="/components/:componentName" element={<ComponentDetails />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
