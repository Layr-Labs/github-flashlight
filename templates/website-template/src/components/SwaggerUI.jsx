import React from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import SwaggerUIReact from 'swagger-ui-react';
import 'swagger-ui-react/swagger-ui.css';
import './SwaggerUI.css';

function SwaggerUI({ components = [] }) {
  const { componentName } = useParams();
  const navigate = useNavigate();
  const component = components.find(c => c.name === componentName);

  if (!component) {
    return (
      <div className="swagger-container">
        <div className="error-state">
          <div className="error-icon">❌</div>
          <h2>Component not found</h2>
          <p>The component "{componentName}" could not be found.</p>
          <Link to="/components" className="button-primary">
            ← Back to Components
          </Link>
        </div>
      </div>
    );
  }

  if (!component.hasApiDocs || !component.openApiSpec) {
    return (
      <div className="swagger-container">
        <div className="error-state">
          <div className="error-icon">📖</div>
          <h2>No API Documentation Available</h2>
          <p>The component "{componentName}" does not have OpenAPI documentation.</p>
          <Link to={`/components/${componentName}`} className="button-primary">
            ← Back to Component Details
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="swagger-container">
      <div className="swagger-header">
        <button onClick={() => navigate(-1)} className="back-button">
          ← Back
        </button>
        <div className="header-content">
          <h1>📖 {component.name} API Documentation</h1>
          <p className="subtitle">Interactive API specification and testing interface</p>
        </div>
        <Link to={`/components/${componentName}`} className="button-secondary">
          View Component Details
        </Link>
      </div>

      <div className="swagger-ui-wrapper">
        <SwaggerUIReact spec={component.openApiSpec} />
      </div>
    </div>
  );
}

export default SwaggerUI;
