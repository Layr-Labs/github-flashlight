import React, { useRef, useEffect, useState } from 'react';
import * as d3 from 'd3';
import { useNavigate } from 'react-router-dom';
import './DependencyGraph.css';

function DependencyGraph({ data = {}, services = [] }) {
  const svgRef = useRef();
  const navigate = useNavigate();
  const [dimensions, setDimensions] = useState({ width: 900, height: 600 });

  useEffect(() => {
    if (!data.nodes || !data.edges || data.nodes.length === 0) {
      return;
    }

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = dimensions.width;
    const height = dimensions.height;

    // Create copies of nodes and edges to avoid mutating props
    const nodes = data.nodes.map(node => ({ ...node }));
    const edges = data.edges.map(edge => ({ ...edge }));

    // Extract third-party services from external_dependencies and add them as nodes
    const thirdPartyServices = new Set();
    data.nodes.forEach(node => {
      if (node.external_dependencies) {
        node.external_dependencies.forEach(dep => {
          thirdPartyServices.add(dep);
        });
      }
    });

    // Add third-party service nodes
    thirdPartyServices.forEach(service => {
      nodes.push({
        id: service,
        classification: 'third-party',
        description: `External service: ${service}`,
        isThirdParty: true
      });
    });

    // Add edges from applications to their external dependencies
    data.nodes.forEach(node => {
      if (node.external_dependencies) {
        node.external_dependencies.forEach(dep => {
          edges.push({
            source: node.id,
            target: dep,
            type: 'external_dependency'
          });
        });
      }
    });

    // Setup zoom
    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });

    svg.call(zoom);

    const g = svg.append('g');

    // Create force simulation
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id(d => d.id).distance(150))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(40));

    // Arrow markers for different edge types
    const edgeTypes = ['default', 'external_dependency', 'grpc', 'gRPC', 'http_api', 'shared_database', 'Shared DynamoDB'];
    svg.append('defs').selectAll('marker')
      .data(edgeTypes)
      .enter().append('marker')
      .attr('id', d => `arrowhead-${d.replace(/\s+/g, '-')}`)
      .attr('viewBox', '-0 -5 10 10')
      .attr('refX', 35)
      .attr('refY', 0)
      .attr('orient', 'auto')
      .attr('markerWidth', 8)
      .attr('markerHeight', 8)
      .append('svg:path')
      .attr('d', 'M 0,-5 L 10 ,0 L 0,5')
      .attr('fill', d => {
        if (d === 'external_dependency') return '#E91E63';
        if (d === 'grpc' || d === 'gRPC') return '#4CAF50';
        if (d === 'http_api') return '#2196F3';
        return '#999';
      });

    // Draw edges
    const link = g.append('g')
      .selectAll('line')
      .data(edges)
      .join('line')
      .attr('stroke', d => {
        if (d.type === 'external_dependency') return '#E91E63';
        if (d.type === 'grpc' || d.type === 'gRPC') return '#4CAF50';
        if (d.type === 'http_api') return '#2196F3';
        return '#999';
      })
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 2)
      .attr('marker-end', d => `url(#arrowhead-${(d.type || 'default').replace(/\s+/g, '-')})`);

    // Color function
    const getNodeColor = (node) => {
      if (node.isThirdParty) {
        return '#FF6B6B';
      }
      if (node.classification === 'application') {
        return '#2196F3';
      }
      return node.phase === 1 ? '#10B981' : '#A855F7';
    };

    // Draw nodes
    const node = g.append('g')
      .selectAll('circle')
      .data(nodes)
      .join('circle')
      .attr('r', d => d.isThirdParty ? 20 : 25)
      .attr('fill', d => getNodeColor(d))
      .attr('stroke', d => d.isThirdParty ? '#EE5A52' : '#fff')
      .attr('stroke-width', 3)
      .attr('stroke-dasharray', d => d.isThirdParty ? '5,5' : 'none')
      .style('cursor', d => d.isThirdParty ? 'default' : 'pointer')
      .call(d3.drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended))
      .on('click', (event, d) => {
        event.stopPropagation();
        if (!d.isThirdParty) {
          navigate(`/components/${d.id}`);
        }
      })
      .on('mouseover', function(event, d) {
        d3.select(this)
          .transition()
          .duration(200)
          .attr('r', 30)
          .attr('stroke-width', 4);

        // Show tooltip
        tooltip.transition()
          .duration(200)
          .style('opacity', .9);

        const service = services.find(s => s.name === d.id);
        const description = service?.description?.substring(0, 100) || 'No description';

        tooltip.html(`
          <strong>${d.id}</strong><br/>
          <em>${d.classification || 'N/A'}</em><br/>
          ${description}${description.length >= 100 ? '...' : ''}
        `)
          .style('left', (event.pageX + 10) + 'px')
          .style('top', (event.pageY - 28) + 'px');
      })
      .on('mouseout', function(event, d) {
        d3.select(this)
          .transition()
          .duration(200)
          .attr('r', 25)
          .attr('stroke-width', 3);

        tooltip.transition()
          .duration(500)
          .style('opacity', 0);
      });

    // Node labels
    const label = g.append('g')
      .selectAll('text')
      .data(nodes)
      .join('text')
      .text(d => d.id)
      .attr('font-size', d => d.isThirdParty ? 9 : 11)
      .attr('dx', 0)
      .attr('dy', d => d.isThirdParty ? 38 : 45)
      .attr('text-anchor', 'middle')
      .style('pointer-events', 'none')
      .style('fill', d => d.isThirdParty ? '#FF6B6B' : '#2D3748')
      .style('font-weight', d => d.isThirdParty ? '700' : '600');

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'graph-tooltip')
      .style('opacity', 0);

    // Update positions on tick
    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      node
        .attr('cx', d => d.x)
        .attr('cy', d => d.y);

      label
        .attr('x', d => d.x)
        .attr('y', d => d.y);
    });

    function dragstarted(event, d) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    }

    function dragged(event, d) {
      d.fx = event.x;
      d.fy = event.y;
    }

    function dragended(event, d) {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    }

    return () => {
      simulation.stop();
      tooltip.remove();
    };
  }, [data, dimensions, navigate, services]);

  if (!data.nodes || data.nodes.length === 0) {
    return (
      <div className="graph-empty">
        <div className="empty-icon">🗺️</div>
        <p>No dependency graph data available</p>
      </div>
    );
  }

  return (
    <div className="dependency-graph">
      <div className="graph-controls">
        <div className="legend">
          <div className="legend-section">
            <strong>Node Types</strong>
            <div className="legend-item">
              <span className="legend-node" style={{ background: '#2196F3', border: '3px solid #fff', borderRadius: '50%' }}></span>
              <span>Applications</span>
            </div>
            <div className="legend-item">
              <span className="legend-node" style={{ background: '#10B981', border: '3px solid #fff', borderRadius: '50%' }}></span>
              <span>Libraries (Phase 1)</span>
            </div>
            <div className="legend-item">
              <span className="legend-node" style={{ background: '#A855F7', border: '3px solid #fff', borderRadius: '50%' }}></span>
              <span>Libraries (Phase 2+)</span>
            </div>
            <div className="legend-item">
              <span className="legend-node" style={{ background: '#FF6B6B', border: '3px dashed #EE5A52', borderRadius: '50%' }}></span>
              <span>Third-Party Services</span>
            </div>
          </div>
          <div className="legend-section">
            <strong>Edge Types</strong>
            <div className="legend-item">
              <span className="legend-color" style={{ background: '#4CAF50' }}></span>
              <span>gRPC</span>
            </div>
            <div className="legend-item">
              <span className="legend-color" style={{ background: '#2196F3' }}></span>
              <span>HTTP API</span>
            </div>
            <div className="legend-item">
              <span className="legend-color" style={{ background: '#E91E63' }}></span>
              <span>External Dependency</span>
            </div>
            <div className="legend-item">
              <span className="legend-color" style={{ background: '#999' }}></span>
              <span>Other</span>
            </div>
          </div>
        </div>
        <div className="graph-hint">
          💡 Click nodes to explore • Drag to reposition • Scroll to zoom
        </div>
      </div>
      <svg
        ref={svgRef}
        width={dimensions.width}
        height={dimensions.height}
        className="graph-svg"
      />
    </div>
  );
}

export default DependencyGraph;
