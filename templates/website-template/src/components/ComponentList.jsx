import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import './ComponentList.css';

function ComponentList({ components = [] }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [filter, setFilter] = useState('all');

  const filteredComponents = components.filter(component => {
    const matchesSearch = component.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         (component.description && component.description.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesFilter = filter === 'all' || component.classification === filter;
    return matchesSearch && matchesFilter;
  });

  return (
    <div className="component-list">
      <div className="list-header">
        <h1>🔍 Component Catalog</h1>
        <p className="subtitle">Browse and explore all applications and libraries in the codebase</p>
      </div>

      <div className="controls">
        <input
          type="text"
          className="search-input"
          placeholder="🔍 Search components..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />

        <div className="filter-buttons">
          <button
            className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            All ({components.length})
          </button>
          <button
            className={`filter-btn ${filter === 'application' ? 'active' : ''}`}
            onClick={() => setFilter('application')}
          >
            🚀 Applications ({components.filter(c => c.classification === 'application').length})
          </button>
          <button
            className={`filter-btn ${filter === 'library' ? 'active' : ''}`}
            onClick={() => setFilter('library')}
          >
            📚 Libraries ({components.filter(c => c.classification === 'library').length})
          </button>
          {components.some(c => c.classification === 'external-service') && (
            <button
              className={`filter-btn ${filter === 'external-service' ? 'active' : ''}`}
              onClick={() => setFilter('external-service')}
            >
              ☁️ External Services ({components.filter(c => c.classification === 'external-service').length})
            </button>
          )}
        </div>
      </div>

      {filteredComponents.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🔍</div>
          <h3>No components found</h3>
          <p>Try adjusting your search or filter</p>
        </div>
      ) : (
        <div className="components-grid">
          {filteredComponents.map(component => (
            <Link
              key={component.name}
              to={`/${component.name}`}
              className="component-card"
            >
              <div className="component-header">
                <h3>{component.name}</h3>
                <span className={`badge ${component.classification}`}>
                  {component.classification === 'application' ? '🚀' : component.classification === 'external-service' ? '☁️' : '📚'} {component.classification}
                </span>
              </div>

              {component.description && (
                <p className="component-description">
                  {component.description.substring(0, 150)}
                  {component.description.length > 150 ? '...' : ''}
                </p>
              )}

              <div className="component-meta">
                <span className="meta-item">
                  <strong>Type:</strong> {component.type || 'N/A'}
                </span>
                {component.hasApiDocs && (
                  <span className="api-badge">📖 API Docs</span>
                )}
                {component.third_party_applications && component.third_party_applications.length > 0 && (
                  <span className="third-party-badge" title={`${component.third_party_applications.length} external service integrations`}>
                    ☁️ {component.third_party_applications.length} external
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default ComponentList;
