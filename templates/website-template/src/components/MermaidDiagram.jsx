import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

// Initialize mermaid with configuration
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  fontFamily: 'monospace',
});

function MermaidDiagram({ chart }) {
  const elementRef = useRef(null);
  const [svg, setSvg] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!chart) return;

    const renderDiagram = async () => {
      try {
        // Generate a unique ID for this diagram
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;

        // Render the diagram
        const { svg: renderedSvg } = await mermaid.render(id, chart);
        setSvg(renderedSvg);
        setError(null);
      } catch (err) {
        console.error('Mermaid rendering error:', err);
        setError(err.message || 'Failed to render diagram');
      }
    };

    renderDiagram();
  }, [chart]);

  if (error) {
    return (
      <div style={{
        padding: '1rem',
        background: '#fee',
        border: '1px solid #fcc',
        borderRadius: '4px',
        color: '#c33',
        fontFamily: 'monospace',
        fontSize: '0.875rem'
      }}>
        <strong>Mermaid Error:</strong> {error}
        <pre style={{ marginTop: '0.5rem', whiteSpace: 'pre-wrap' }}>
          {chart}
        </pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div style={{
        padding: '1rem',
        textAlign: 'center',
        color: '#666'
      }}>
        Loading diagram...
      </div>
    );
  }

  return (
    <div
      ref={elementRef}
      className="mermaid-diagram"
      style={{
        margin: '1rem 0',
        padding: '1rem',
        background: '#fff',
        borderRadius: '8px',
        border: '1px solid #e5e7eb',
        overflow: 'auto'
      }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

export default MermaidDiagram;
