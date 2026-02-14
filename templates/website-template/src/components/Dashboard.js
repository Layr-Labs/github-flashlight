import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import hljs from 'highlight.js';
import MermaidDiagram from './MermaidDiagram';
import analysisData from '../data/analysisData';
import summaryMarkdown from '../data/summaryMarkdown';
import '../styles/Dashboard.css';
import 'highlight.js/styles/github-dark.css';

// Helper function to parse markdown subsections based on H3 headers
function parseSubsections(content) {
  const subsections = [];
  const lines = content.split('\n');
  let currentSubsection = null;
  let currentContent = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith('### ')) {
      if (currentSubsection) {
        subsections.push({
          title: currentSubsection,
          content: currentContent.join('\n').trim()
        });
      }
      currentSubsection = line.substring(4).trim();
      currentContent = [];
    } else if (currentSubsection) {
      currentContent.push(line);
    }
  }

  if (currentSubsection) {
    subsections.push({
      title: currentSubsection,
      content: currentContent.join('\n').trim()
    });
  }

  return subsections;
}

// Helper function to parse markdown into sections based on H2 headers
function parseMarkdownSections(markdown) {
  if (!markdown) return [];

  markdown = markdown.replace(/\\`/g, '`');

  const sections = [];
  const lines = markdown.split('\n');
  let currentSection = null;
  let currentContent = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith('## ')) {
      if (currentSection) {
        const content = currentContent.join('\n').trim();
        sections.push({
          title: currentSection,
          content: content,
          subsections: parseSubsections(content)
        });
      }
      currentSection = line.substring(3).trim();
      currentContent = [];
    } else if (currentSection) {
      currentContent.push(line);
    }
  }

  if (currentSection) {
    const content = currentContent.join('\n').trim();
    sections.push({
      title: currentSection,
      content: content,
      subsections: parseSubsections(content)
    });
  }

  return sections;
}

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
          <div className="stat-card">
            <div className="stat-number">{architecture.patterns.length}</div>
            <div className="stat-label">Architecture Patterns</div>
          </div>
        </div>
      </section>

      {/* Interactive System Flow Visualization */}
      <section className="overview-section">
        <h3>System Architecture Flow</h3>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '1.5rem',
          alignItems: 'center',
          padding: '2rem',
          background: 'white',
          borderRadius: '8px',
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)'
        }}>
          {[
            { label: 'Rollups/Clients', desc: 'External blockchain rollup systems requesting data availability', color: '#667eea' },
            { label: 'Proxy (REST/JSON-RPC)', desc: 'API gateway handling client requests', color: '#764ba2' },
            { label: 'Disperser Services', desc: 'API, Batcher, Encoder, Controller - process and prepare data', color: '#667eea' },
            { label: 'DA Nodes (Operators)', desc: 'Distributed operators storing encoded data', color: '#764ba2' },
            { label: 'Retriever Service', desc: 'Reconstructs data from DA nodes', color: '#667eea' },
            { label: 'Rollups/Clients', desc: 'Receive reconstructed data', color: '#764ba2' }
          ].map((node, index, arr) => (
            <React.Fragment key={index}>
              <div
                style={{
                  width: '100%',
                  maxWidth: '500px',
                  padding: '1.5rem',
                  background: `linear-gradient(135deg, ${node.color} 0%, ${node.color}dd 100%)`,
                  color: 'white',
                  borderRadius: '8px',
                  textAlign: 'center',
                  cursor: 'pointer',
                  transition: 'all 0.3s ease',
                  boxShadow: '0 4px 12px rgba(102, 126, 234, 0.3)',
                  position: 'relative'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'scale(1.05) translateY(-5px)';
                  e.currentTarget.style.boxShadow = '0 8px 24px rgba(102, 126, 234, 0.5)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'scale(1) translateY(0)';
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(102, 126, 234, 0.3)';
                }}
                title={node.desc}
              >
                <div style={{ fontSize: '1.2rem', fontWeight: '700', marginBottom: '0.5rem' }}>
                  {node.label}
                </div>
                <div style={{ fontSize: '0.9rem', opacity: 0.9 }}>
                  {node.desc}
                </div>
              </div>
              {index < arr.length - 1 && (
                <div style={{
                  fontSize: '2rem',
                  color: '#667eea',
                  fontWeight: 'bold',
                  animation: 'bounce 2s infinite'
                }}>
                  ↓
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
        <style>{`
          @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-10px); }
          }
        `}</style>
      </section>

      {dataFlowsSection && dataFlowsSection.subsections && dataFlowsSection.subsections.length > 0 && (
        <section className="key-flows-section">
          <h3>Data Flows</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            {dataFlowsSection.subsections.map((flowSubsection, i) => {
              // Parse steps from the subsection content - look for lines with arrows
              const lines = flowSubsection.content.split('\n');
              const flowLine = lines.find(line => line.includes('→') || line.includes('->'));

              if (!flowLine) return null;

              const steps = flowLine
                .split(/→|->/)
                .map(s => s.trim())
                .filter(s => s.length > 0);

              return (
                <div key={i} style={{
                  background: 'white',
                  padding: '2rem',
                  borderRadius: '8px',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
                  border: '2px solid #e5e7eb'
                }}>
                  <h4 style={{
                    fontSize: '1.3rem',
                    fontWeight: '700',
                    color: '#1f2937',
                    marginBottom: '1.5rem',
                    borderBottom: '2px solid #667eea',
                    paddingBottom: '0.5rem'
                  }}>
                    {flowSubsection.title}
                  </h4>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '1rem',
                    flexWrap: 'wrap',
                    justifyContent: 'center'
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
                </div>
              );
            }).filter(Boolean)}
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

      <section className="tech-stack-section">
        <h3>Technology Stack</h3>
        <div className="tech-grid">
          <div className="tech-category">
            <h4>Languages</h4>
            <ul>
              {architecture.techStack.languages.map((lang, i) => (
                <li key={i}>{lang}</li>
              ))}
            </ul>
          </div>
          <div className="tech-category">
            <h4>Frameworks</h4>
            <ul>
              {architecture.techStack.frameworks.map((fw, i) => (
                <li key={i}>{fw}</li>
              ))}
            </ul>
          </div>
          <div className="tech-category">
            <h4>Databases</h4>
            <ul>
              {architecture.techStack.databases.map((db, i) => (
                <li key={i}>{db}</li>
              ))}
            </ul>
          </div>
          <div className="tech-category">
            <h4>Cryptography</h4>
            <ul>
              {architecture.techStack.cryptography.map((crypto, i) => (
                <li key={i}>{crypto}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

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
                        <div className="markdown-content">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              code({ node, inline, className, children, ...props }) {
                                const match = /language-(\w+)/.exec(className || '');
                                const language = match ? match[1] : '';
                                const codeString = String(children).replace(/\n$/, '');

                                if (!inline && language === 'mermaid') {
                                  return <MermaidDiagram chart={codeString} />;
                                }

                                if (!inline && language) {
                                  try {
                                    const highlighted = hljs.highlight(codeString, {
                                      language: language,
                                      ignoreIllegals: true
                                    });
                                    return (
                                      <code
                                        className={`${className} hljs`}
                                        dangerouslySetInnerHTML={{ __html: highlighted.value }}
                                        {...props}
                                      />
                                    );
                                  } catch (e) {
                                    return (
                                      <code className={className} {...props}>
                                        {children}
                                      </code>
                                    );
                                  }
                                }

                                return (
                                  <code className={className} {...props}>
                                    {children}
                                  </code>
                                );
                              }
                            }}
                          >
                            {subsection.content}
                          </ReactMarkdown>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="markdown-content">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    code({ node, inline, className, children, ...props }) {
                      const match = /language-(\w+)/.exec(className || '');
                      const language = match ? match[1] : '';
                      const codeString = String(children).replace(/\n$/, '');

                      if (!inline && language === 'mermaid') {
                        return <MermaidDiagram chart={codeString} />;
                      }

                      if (!inline && language) {
                        try {
                          const highlighted = hljs.highlight(codeString, {
                            language: language,
                            ignoreIllegals: true
                          });
                          return (
                            <code
                              className={`${className} hljs`}
                              dangerouslySetInnerHTML={{ __html: highlighted.value }}
                              {...props}
                            />
                          );
                        } catch (e) {
                          return (
                            <code className={className} {...props}>
                              {children}
                            </code>
                          );
                        }
                      }

                      return (
                        <code className={className} {...props}>
                          {children}
                        </code>
                      );
                    }
                  }}
                >
                  {section.content}
                </ReactMarkdown>
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}

export default Dashboard;
