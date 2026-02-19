import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import hljs from 'highlight.js';
import MermaidDiagram from './MermaidDiagram';
import analysisData from '../data/analysisData';
import markdownContent from '../data/markdownContent';
import '../styles/ComponentDetails.css';
import 'highlight.js/styles/github-dark.css';

// Helper function to parse markdown subsections based on H3 headers
function parseSubsections(content) {
  const subsections = [];
  const lines = content.split('\n');
  let currentSubsection = null;
  let currentContent = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Check if this is an H3 header (### Subsection Name)
    if (line.startsWith('### ')) {
      // Save previous subsection if exists
      if (currentSubsection) {
        subsections.push({
          title: currentSubsection,
          content: currentContent.join('\n').trim()
        });
      }

      // Start new subsection
      currentSubsection = line.substring(4).trim();
      currentContent = [];
    } else if (currentSubsection) {
      // Add line to current subsection content
      currentContent.push(line);
    }
    // Skip lines before the first H3
  }

  // Add the last subsection
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

  // Unescape backticks for proper code rendering (both single and triple)
  markdown = markdown.replace(/\\`/g, '`');

  const sections = [];
  const lines = markdown.split('\n');
  let currentSection = null;
  let currentContent = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Check if this is an H2 header (## Section Name)
    if (line.startsWith('## ')) {
      // Save previous section if exists
      if (currentSection) {
        const content = currentContent.join('\n').trim();
        sections.push({
          title: currentSection,
          content: content,
          subsections: parseSubsections(content)
        });
      }

      // Start new section
      currentSection = line.substring(3).trim();
      currentContent = [];
    } else if (currentSection) {
      // Add line to current section content
      currentContent.push(line);
    }
    // Skip lines before the first H2 (title, metadata, etc.)
  }

  // Add the last section
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

function ComponentDetails({ searchQuery }) {
  const { componentName } = useParams();
  const [selectedComponent, setSelectedComponent] = useState(null);
  const [filteredComponents, setFilteredComponents] = useState([]);
  const [expandedSubsections, setExpandedSubsections] = useState({});
  const [expandedSections, setExpandedSections] = useState({});

  useEffect(() => {
    const filtered = analysisData.components.filter(c =>
      !searchQuery || c.name.toLowerCase().includes(searchQuery.toLowerCase())
    );
    setFilteredComponents(filtered);
  }, [searchQuery]);

  useEffect(() => {
    if (componentName) {
      const component = analysisData.components.find(c => c.name === componentName);
      setSelectedComponent(component);

      // Set default expanded sections for Data Flows and API Surface
      if (component) {
        const rawMarkdown = markdownContent[component.name] || markdownContent[component.name + '_application'] || '';
        let sections = parseMarkdownSections(rawMarkdown);

        // Reorder sections the same way as in render (Data Flows first, then API Surface)
        const dataFlowsIndex = sections.findIndex(s => s.title.toLowerCase().includes('data flow'));
        if (dataFlowsIndex > 0) {
          const dataFlowsSection = sections.splice(dataFlowsIndex, 1)[0];
          sections.unshift(dataFlowsSection);
        }

        const apiSurfaceIndex = sections.findIndex(s => s.title.toLowerCase().includes('api surface'));
        if (apiSurfaceIndex > 1) {
          const apiSurfaceSection = sections.splice(apiSurfaceIndex, 1)[0];
          sections.splice(1, 0, apiSurfaceSection);
        }

        // Now set expanded state based on reordered sections
        const defaultExpanded = {};
        const defaultExpandedSubsections = {};

        sections.forEach((section, index) => {
          const title = section.title.toLowerCase();
          // Expand Data Flows and API Surface by default
          if (title.includes('data flow') || title.includes('api surface')) {
            defaultExpanded[index] = true;

            // Also expand the first subsection of Data Flows
            if (title.includes('data flow') && section.subsections && section.subsections.length > 0) {
              defaultExpandedSubsections[`${index}-0`] = true;
            }
          }
        });

        setExpandedSections(defaultExpanded);
        setExpandedSubsections(defaultExpandedSubsections);
      } else {
        setExpandedSections({});
        setExpandedSubsections({});
      }
    }
  }, [componentName]);

  const toggleSubsection = (sectionIndex, subsectionIndex) => {
    const key = `${sectionIndex}-${subsectionIndex}`;
    setExpandedSubsections(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const toggleSection = (sectionIndex) => {
    setExpandedSections(prev => ({
      ...prev,
      [sectionIndex]: !prev[sectionIndex]
    }));
  };

  if (componentName && !selectedComponent) {
    return (
      <div className="component-details">
        <div className="not-found">
          <h2>Component Not Found</h2>
          <p>The component "{componentName}" could not be found.</p>
          <Link to="/" className="back-link">← Back to dashboard</Link>
        </div>
      </div>
    );
  }

  if (selectedComponent) {
    const dependencies = [];
    const dependents = [];

    // Find dependencies and dependents from library graph
    analysisData.libraryGraph.edges.forEach(edge => {
      if (edge.source === selectedComponent.name || (edge.source.name && edge.source.name === selectedComponent.name)) {
        const targetName = edge.target.name || edge.target;
        dependencies.push(analysisData.components.find(c => c.name === targetName));
      }
      if (edge.target === selectedComponent.name || (edge.target.name && edge.target.name === selectedComponent.name)) {
        const sourceName = edge.source.name || edge.source;
        dependents.push(analysisData.components.find(c => c.name === sourceName));
      }
    });

    // Find interactions from application graph
    const interactions = [];
    analysisData.applicationGraph.edges.forEach(edge => {
      const sourceName = edge.source.name || edge.source;
      const targetName = edge.target.name || edge.target;

      if (sourceName === selectedComponent.name || targetName === selectedComponent.name) {
        interactions.push({
          from: sourceName,
          to: targetName,
          type: edge.type,
          description: edge.description
        });
      }
    });

    // Parse markdown content into sections
    const rawMarkdown = markdownContent[selectedComponent.name] || markdownContent[selectedComponent.name + '_application'] || '';
    let markdownSections = parseMarkdownSections(rawMarkdown);

    // Reorder sections: Data Flows first, then API Surface
    const dataFlowsIndex = markdownSections.findIndex(s => s.title.toLowerCase().includes('data flow'));
    const apiSurfaceIndex = markdownSections.findIndex(s => s.title.toLowerCase().includes('api surface'));

    // Move Data Flows to the top
    if (dataFlowsIndex > 0) {
      const dataFlowsSection = markdownSections.splice(dataFlowsIndex, 1)[0];
      markdownSections.unshift(dataFlowsSection);
    }

    // Move API Surface to second position (after Data Flows)
    const newApiSurfaceIndex = markdownSections.findIndex(s => s.title.toLowerCase().includes('api surface'));
    if (newApiSurfaceIndex > 1) {
      const apiSurfaceSection = markdownSections.splice(newApiSurfaceIndex, 1)[0];
      markdownSections.splice(1, 0, apiSurfaceSection);
    }

    return (
      <div className="component-details">
        <div className="component-header">
          <Link to="/" className="back-link">← Back to dashboard</Link>
          <h1>{selectedComponent.name}</h1>
          <div className="component-badges">
            <span className={`badge ${selectedComponent.classification}`}>
              {selectedComponent.classification}
            </span>
            <span className="badge type">{selectedComponent.type}</span>
          </div>
        </div>

        <div className="component-content">
          <section className="section">
            <h2>Overview</h2>
            <p>{selectedComponent.description}</p>
          </section>

          {dependencies.length > 0 && (
            <section className="section">
              <h2>Dependencies</h2>
              <p className="section-subtitle">This component depends on:</p>
              <ul className="dependency-list">
                {dependencies.map((dep, i) => dep && (
                  <li key={i}>
                    <Link to={`/${dep.name}`} className="dependency-link">
                      {dep.name}
                    </Link>
                    <span className="dependency-desc">{dep.description}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {dependents.length > 0 && (
            <section className="section">
              <h2>Dependents</h2>
              <p className="section-subtitle">Components that depend on this:</p>
              <ul className="dependency-list">
                {dependents.map((dep, i) => dep && (
                  <li key={i}>
                    <Link to={`/${dep.name}`} className="dependency-link">
                      {dep.name}
                    </Link>
                    <span className="dependency-desc">{dep.description}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {interactions.length > 0 && (
            <section className="section">
              <h2>Interactions</h2>
              <p className="section-subtitle">Communication with other applications:</p>
              <div className="interactions-list">
                {interactions.map((interaction, i) => (
                  <div key={i} className="interaction-card">
                    <div className="interaction-flow">
                      <Link to={`/${interaction.from}`} className="interaction-node">
                        {interaction.from}
                      </Link>
                      <span className="interaction-arrow">→</span>
                      <Link to={`/${interaction.to}`} className="interaction-node">
                        {interaction.to}
                      </Link>
                    </div>
                    <div className="interaction-meta">
                      <span className="interaction-type">{interaction.type}</span>
                      <span className="interaction-desc">{interaction.description}</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {markdownSections.map((section, index) => {
            const isSectionExpanded = expandedSections[index];

            return (
              <section key={index} className="section markdown-section">
                <div className="section-header-with-toggle">
                  <h2>{section.title}</h2>
                  <button
                    className="section-toggle"
                    onClick={() => toggleSection(index)}
                    aria-label={isSectionExpanded ? "Collapse" : "Expand"}
                  >
                    {isSectionExpanded ? "−" : "+"}
                  </button>
                </div>

                {isSectionExpanded && (
                  <>
                    {section.subsections.length > 0 ? (
                // Render subsections as separate cards
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

                                  // Handle mermaid diagrams
                                  if (!inline && language === 'mermaid') {
                                    return <MermaidDiagram chart={codeString} />;
                                  }

                                  // Handle code blocks with syntax highlighting
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
                                      // Fallback if language not supported
                                      return (
                                        <code className={className} {...props}>
                                          {children}
                                        </code>
                                      );
                                    }
                                  }

                                  // Inline code
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
                // Render section content normally if no subsections
                <div className="markdown-content">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      code({ node, inline, className, children, ...props }) {
                        const match = /language-(\w+)/.exec(className || '');
                        const language = match ? match[1] : '';
                        const codeString = String(children).replace(/\n$/, '');

                        // Handle mermaid diagrams
                        if (!inline && language === 'mermaid') {
                          return <MermaidDiagram chart={codeString} />;
                        }

                        // Handle code blocks with syntax highlighting
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
                            // Fallback if language not supported
                            return (
                              <code className={className} {...props}>
                                {children}
                              </code>
                            );
                          }
                        }

                        // Inline code
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
                  </>
                )}
              </section>
            );
          })}
        </div>
      </div>
    );
  }

  // Component list view
  const applications = filteredComponents.filter(c => c.classification === 'application');
  const libraries = filteredComponents.filter(c => c.classification === 'library');

  return (
    <div className="component-list-view">
      <div className="list-header">
        <h1>All Components</h1>
        <p>Browse all {analysisData.components.length} components in the codebase</p>
      </div>

      {applications.length > 0 && (
        <section className="component-category">
          <h2>Applications ({applications.length})</h2>
          <div className="component-grid">
            {applications.map((component, i) => (
              <Link
                key={i}
                to={`/${component.name}`}
                className="component-card"
              >
                <div className="component-card-header">
                  <h3>{component.name}</h3>
                  <span className="component-card-type">{component.type}</span>
                </div>
                <p className="component-card-desc">{component.description}</p>
              </Link>
            ))}
          </div>
        </section>
      )}

      {libraries.length > 0 && (
        <section className="component-category">
          <h2>Libraries ({libraries.length})</h2>
          <div className="component-grid">
            {libraries.map((component, i) => (
              <Link
                key={i}
                to={`/${component.name}`}
                className="component-card"
              >
                <div className="component-card-header">
                  <h3>{component.name}</h3>
                  <span className="component-card-type">{component.type}</span>
                </div>
                <p className="component-card-desc">{component.description}</p>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default ComponentDetails;
