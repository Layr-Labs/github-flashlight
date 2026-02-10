import React from 'react';
import { Link } from 'react-router-dom';
import DependencyGraph from './DependencyGraph';
import MarkdownContent from './MarkdownContent';
import './ArchitectureOverview.css';

function ArchitectureOverview({ data }) {
  const { services = [], dependencyGraph = {}, architecture = {}, metadata = {} } = data;

  const applicationCount = services.filter(s => s.classification === 'application').length;
  const libraryCount = services.filter(s => s.classification === 'library').length;
  const servicesWithAPIs = services.filter(s => s.hasApiDocs).length;

  // Count unique third-party integrations
  const thirdPartyServices = new Set();
  services.forEach(service => {
    if (service.third_party_applications && Array.isArray(service.third_party_applications)) {
      service.third_party_applications.forEach(tp => {
        if (tp.name) thirdPartyServices.add(tp.name);
      });
    }
  });
  const thirdPartyCount = thirdPartyServices.size;

  return (
    <div className="architecture-overview">
      <div className="hero">
        <h1>👋 Welcome to your codebase!</h1>
        <p className="subtitle">Explore your applications, libraries, dependencies, and architecture</p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">🎯</div>
          <div className="stat-value">{services.length}</div>
          <div className="stat-label">Total Components</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">🚀</div>
          <div className="stat-value">{applicationCount}</div>
          <div className="stat-label">Applications</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">📚</div>
          <div className="stat-value">{libraryCount}</div>
          <div className="stat-label">Libraries</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">📖</div>
          <div className="stat-value">{servicesWithAPIs}</div>
          <div className="stat-label">With API Docs</div>
        </div>
        {thirdPartyCount > 0 && (
          <div className="stat-card third-party">
            <div className="stat-icon">☁️</div>
            <div className="stat-value">{thirdPartyCount}</div>
            <div className="stat-label">External Services</div>
          </div>
        )}
      </div>

      {architecture.overview && (
        <div className="card overview-card">
          <h2>System Overview</h2>
          <MarkdownContent content={architecture.overview} />
        </div>
      )}

      <div className="graph-section">
        <h2>🗺️ Dependency Graph</h2>
        <p className="graph-description">
          Interactive visualization of component dependencies. Click nodes to explore, drag to reposition, scroll to zoom.
        </p>
        <DependencyGraph data={dependencyGraph} services={services} />
      </div>

      <div className="cta-section">
        <h2>Ready to explore?</h2>
        <Link to="/components" className="button-primary">
          🔍 Browse All Components
        </Link>
      </div>
    </div>
  );
}

export default ArchitectureOverview;
