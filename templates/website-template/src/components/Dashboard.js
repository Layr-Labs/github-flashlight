import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import MarkdownContent from './MarkdownContent';
import analysisData from '../data/analysisData';
import summaryMarkdown from '../data/summaryMarkdown';
import { parseMarkdownSections, parseSubsections } from '../utils/markdownParser';
import '../styles/Dashboard.css';


function Dashboard() {
  const { metadata, architecture, components } = analysisData;
  const [expandedSubsections, setExpandedSubsections] = useState({});

  const applications = components.filter(c => c.classification === 'application');
  const libraries = components.filter(c => c.classification === 'library');

  // Parse all sections first to extract Data Flows for visualization
  const allSections = parseMarkdownSections(summaryMarkdown);

  // Find the Data Flows section for the interactive visualization
  const dataFlowsSection = allSections.find(section =>
    section.title.toLowerCase().includes('data flow')
  );

  // Then filter out hidden sections for the markdown display at the bottom
  const hiddenSections = [
    'executive summary',
    'system architecture',
    'key technologies',
    'data flows',
    'deployment architecture',
    'security considerations',
    'component directory',
    'next steps',
    'analysis files',
    'performance characteristics'
  ];

  const markdownSections = allSections
    .filter(section => !hiddenSections.includes(section.title.toLowerCase()));

  const toggleSubsection = (sectionIndex, subsectionIndex) => {
    const key = `${sectionIndex}-${subsectionIndex}`;
    setExpandedSubsections(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  return (
    <div className="dashboard">
      <section className="hero-section">
        <h2>{metadata.projectName}</h2>
        <p className="hero-description">{metadata.description}</p>
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-number">{metadata.totalComponents}</div>
            <div className="stat-label">Total Components</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">{metadata.totalApplications}</div>
            <div className="stat-label">Applications</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">{metadata.totalLibraries}</div>
            <div className="stat-label">Libraries</div>
          </div>
          {architecture.patterns && architecture.patterns.length > 0 && (
            <div className="stat-card">
              <div className="stat-number">{architecture.patterns.length}</div>
              <div className="stat-label">Architecture Patterns</div>
            </div>
          )}
        </div>
      </section>

      {/* Architecture overview from markdown */}
      {architecture.overview && (
        <section className="overview-section">
          <h3>Architecture Overview</h3>
          <MarkdownContent content={architecture.overview} />
        </section>
      )}

      {dataFlowsSection && dataFlowsSection.subsections && dataFlowsSection.subsections.length > 0 && (
        <section className="key-flows-section">
          <h3>Major Data Flows</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            {dataFlowsSection.subsections.map((flowSubsection, i) => {
              // Parse steps from the subsection content - look for lines with arrows
              const lines = flowSubsection.content.split('\n');
              const flowLine = lines.find(line => line.includes('→') || line.includes('->'));

              const steps = flowLine
                ? flowLine.split(/→|->/).map(s => s.trim()).filter(s => s.length > 0)
                : [];

              const flowKey = `flow-${i}`;
              const isExpanded = expandedSubsections[flowKey];

              return (
                <div key={i} style={{
                  background: 'white',
                  padding: '2rem',
                  borderRadius: '8px',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
                  border: '2px solid #e5e7eb'
                }}>
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: steps.length > 0 || isExpanded ? '1.5rem' : 0
                  }}>
                    <h4 style={{
                      fontSize: '1.3rem',
                      fontWeight: '700',
                      color: '#1f2937',
                      borderBottom: '2px solid #667eea',
                      paddingBottom: '0.5rem',
                      margin: 0
                    }}>
                      {flowSubsection.title}
                    </h4>
                    <button
                      className="subsection-toggle"
                      onClick={() => {
                        setExpandedSubsections(prev => ({
                          ...prev,
                          [flowKey]: !prev[flowKey]
                        }));
                      }}
                      aria-label={isExpanded ? "Collapse" : "Expand"}
                    >
                      {isExpanded ? "−" : "+"}
                    </button>
                  </div>

                  {steps.length > 0 && (
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '1rem',
                      flexWrap: 'wrap',
                      justifyContent: 'center',
                      marginBottom: isExpanded ? '1.5rem' : 0
                    }}>
                      {steps.map((step, stepIndex) => (
                        <React.Fragment key={stepIndex}>
                          <div
                            style={{
                              padding: '1rem 1.5rem',
                              background: `linear-gradient(135deg, ${stepIndex % 2 === 0 ? '#667eea' : '#764ba2'} 0%, ${stepIndex % 2 === 0 ? '#667eeadd' : '#764ba2dd'} 100%)`,
                              color: 'white',
                              borderRadius: '6px',
                              fontWeight: '600',
                              fontSize: '0.95rem',
                              cursor: 'pointer',
                              transition: 'all 0.3s ease',
                              boxShadow: '0 2px 8px rgba(102, 126, 234, 0.3)',
                              minWidth: '140px',
                              textAlign: 'center',
                              position: 'relative'
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.transform = 'scale(1.05) translateY(-3px)';
                              e.currentTarget.style.boxShadow = '0 6px 16px rgba(102, 126, 234, 0.5)';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.transform = 'scale(1) translateY(0)';
                              e.currentTarget.style.boxShadow = '0 2px 8px rgba(102, 126, 234, 0.3)';
                            }}
                          >
                            <div style={{ fontSize: '0.75rem', opacity: 0.8, marginBottom: '0.25rem' }}>
                              Step {stepIndex + 1}
                            </div>
                            {step}
                          </div>
                          {stepIndex < steps.length - 1 && (
                            <div style={{
                              fontSize: '1.5rem',
                              color: '#667eea',
                              fontWeight: 'bold'
                            }}>
                              →
                            </div>
                          )}
                        </React.Fragment>
                      ))}
                    </div>
                  )}

                  {isExpanded && (
                    <MarkdownContent content={flowSubsection.content} />
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      <section className="components-section">
        <h3>Component Categories</h3>
        <div className="component-categories">
          <div className="category-box">
            <h4>Applications ({applications.length})</h4>
            <ul className="component-list">
              {applications.map((comp, i) => (
                <li key={i}>
                  <Link to={`/${comp.name}`} className="component-link">
                    {comp.name}
                  </Link>
                  <span className="component-type">{comp.type}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="category-box">
            <h4>Libraries ({libraries.length})</h4>
            <ul className="component-list">
              {libraries.map((comp, i) => (
                <li key={i}>
                  <Link to={`/${comp.name}`} className="component-link">
                    {comp.name}
                  </Link>
                  <span className="component-type">{comp.type}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {architecture.techStack && (
        <section className="tech-stack-section">
          <h3>Technology Stack</h3>
          <div className="tech-grid">
            {Object.entries(architecture.techStack)
              .filter(([, items]) => Array.isArray(items) && items.length > 0)
              .map(([category, items]) => (
                <div key={category} className="tech-category">
                  <h4>{category.charAt(0).toUpperCase() + category.slice(1)}</h4>
                  <ul>
                    {items.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
              ))}
          </div>
        </section>
      )}

      {architecture.patterns && architecture.patterns.length > 0 && (
        <section className="patterns-section">
          <h3>Architecture Patterns</h3>
          <div className="patterns-grid">
            {architecture.patterns.map((pattern, i) => (
              <div key={i} className="pattern-card">
                {pattern}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="quick-links-section">
        <h3>Explore</h3>
        <div className="quick-links">
          <Link to="/library-graph" className="quick-link-card">
            <h4>Library Graph</h4>
            <p>View the dependency graph of all libraries</p>
          </Link>
          <Link to="/application-graph" className="quick-link-card">
            <h4>Application Graph</h4>
            <p>Explore how applications communicate</p>
          </Link>
        </div>
      </section>

      {/* Analysis Summary Sections */}
      <div className="analysis-summary-sections">
        {markdownSections.map((section, index) => (
          <section key={index} className="section markdown-section">
            <h2>{section.title}</h2>

            {section.subsections.length > 0 ? (
              <div className="subsections-container">
                {section.subsections.map((subsection, subIndex) => {
                  const key = `${index}-${subIndex}`;
                  const isExpanded = expandedSubsections[key];

                  return (
                    <div key={subIndex} className="subsection-card">
                      <div className="subsection-header">
                        <h3 className="subsection-title">{subsection.title}</h3>
                        <button
                          className="subsection-toggle"
                          onClick={() => toggleSubsection(index, subIndex)}
                          aria-label={isExpanded ? "Collapse" : "Expand"}
                        >
                          {isExpanded ? "−" : "+"}
                        </button>
                      </div>

                      {isExpanded && (
                        <MarkdownContent content={subsection.content} />
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <MarkdownContent content={section.content} />
            )}
          </section>
        ))}
      </div>
    </div>
  );
}

export default Dashboard;
