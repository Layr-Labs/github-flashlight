import React from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import MarkdownContent from './MarkdownContent';
import './ComponentDetail.css';

function ComponentDetail({ components = [] }) {
  const { componentName } = useParams();
  const navigate = useNavigate();
  const component = components.find(c => c.name === componentName);

  if (!component) {
    return (
      <div className="component-detail">
        <div className="error-state">
          <div className="error-icon">❌</div>
          <h2>Component not found</h2>
          <p>The component "{componentName}" could not be found.</p>
          <Link to="/" className="button-primary">
            ← Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="component-detail">
      <button onClick={() => navigate(-1)} className="back-button">
        ← Back
      </button>

      <div className="detail-header">
        <div>
          <h1>{component.name}</h1>
          <div className="header-badges">
            <span className={`badge ${component.classification}`}>
              {component.classification === 'application' ? '🚀' : '📚'} {component.classification}
            </span>
            {component.type && (
              <span className="badge-type">{component.type}</span>
            )}
          </div>
        </div>
        {component.hasApiDocs && (
          <Link to={`/${component.name}/api`} className="button-primary">
            📖 View API Documentation
          </Link>
        )}
      </div>

      {component.description && (
        <div className="card description-card">
          <h2>Description</h2>
          <MarkdownContent content={component.description} />
        </div>
      )}

      {component.architecture && (
        <div className="card">
          <h2>🏗️ Architecture</h2>
          <MarkdownContent content={component.architecture} />
        </div>
      )}

      {component.key_components && component.key_components.length > 0 && (
        <div className="card">
          <h2>🔧 Key Components</h2>
          <ul className="key-components-list">
            {component.key_components.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {component.systemFlows && (
        <div className="card">
          <h2>🔄 System Flows</h2>
          {Array.isArray(component.systemFlows) ? (
            <ul className="flow-list">
              {component.systemFlows.map((flow, idx) => (
                <li key={idx}>{flow}</li>
              ))}
            </ul>
          ) : (
            <MarkdownContent content={component.systemFlows} />
          )}
        </div>
      )}

      {component.dataFlows && (
        <div className="card">
          <h2>🌊 Data Flows</h2>
          <MarkdownContent content={component.dataFlows} />
        </div>
      )}

      {component.externalDependencies && (
        <div className="card">
          <h2>📦 External Dependencies</h2>
          <MarkdownContent content={component.externalDependencies} />
        </div>
      )}

      {component.internalDependencies && (
        <div className="card">
          <h2>🔗 Internal Dependencies</h2>
          <MarkdownContent content={component.internalDependencies} />
        </div>
      )}

      {component.libraries_used && component.libraries_used.length > 0 && (
        <div className="card">
          <h2>📚 Libraries Used</h2>
          <ul className="dependency-list">
            {component.libraries_used.map((lib, idx) => (
              <li key={idx}>{lib}</li>
            ))}
          </ul>
        </div>
      )}

      {component.external_dependencies && component.external_dependencies.length > 0 && (
        <div className="card">
          <h2>🔗 External Dependencies (Legacy)</h2>
          <ul className="dependency-list">
            {component.external_dependencies.map((dep, idx) => (
              <li key={idx}>{dep}</li>
            ))}
          </ul>
        </div>
      )}

      {component.application_interactions && component.application_interactions.length > 0 && (
        <div className="card">
          <h2>🌐 Application Interactions</h2>
          <div className="interactions-list">
            {component.application_interactions.map((interaction, idx) => (
              <div key={idx} className="interaction-card">
                <h4>{interaction.target}</h4>
                <span className="interaction-type">{interaction.type}</span>
                <p>{interaction.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {component.third_party_applications && component.third_party_applications.length > 0 && (
        <div className="card">
          <h2>☁️ Third-Party Integrations</h2>
          <div className="interactions-list">
            {component.third_party_applications.map((integration, idx) => (
              <div key={idx} className="interaction-card third-party">
                <h4>{integration.name}</h4>
                <span className="interaction-type service-type">{integration.type}</span>
                <p className="description">{integration.description}</p>
                <p className="integration-method">
                  <strong>Integration:</strong> {integration.integration_method}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {component.api_surface && (
        <div className="card">
          <h2>🔌 API Surface</h2>
          <MarkdownContent content={component.api_surface} />
        </div>
      )}
    </div>
  );
}

export default ComponentDetail;
