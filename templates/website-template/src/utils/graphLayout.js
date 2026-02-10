/**
 * Utility functions for D3.js graph layout and transformations
 */

/**
 * Transform dependency graph data for D3.js consumption
 * @param {Object} graphData - Raw dependency graph data
 * @returns {Object} Transformed graph with nodes and edges
 */
export function transformGraphData(graphData) {
  if (!graphData || !graphData.nodes || !graphData.edges) {
    return { nodes: [], edges: [] };
  }

  // Ensure each node has required properties
  const nodes = graphData.nodes.map(node => ({
    id: node.id,
    classification: node.classification || 'library',
    type: node.type || 'unknown',
    phase: node.phase || 1,
    ...node
  }));

  // Transform edges to use source/target
  const edges = graphData.edges.map(edge => ({
    source: edge.from || edge.source,
    target: edge.to || edge.target,
    ...edge
  }));

  return { nodes, edges };
}

/**
 * Calculate node color based on classification and phase
 * @param {Object} node - Graph node
 * @returns {string} Color hex code
 */
export function getNodeColor(node) {
  if (node.classification === 'application') {
    return '#FF6B6B'; // Coral red for applications
  }

  // Libraries colored by phase
  return node.phase === 1 ? '#10B981' : '#A855F7'; // Green for Phase 1, Purple for Phase 2+
}

/**
 * Calculate node size based on metrics
 * @param {Object} node - Graph node
 * @returns {number} Node radius
 */
export function getNodeSize(node) {
  const baseSize = 25;
  const dependentCount = node.usedBy?.length || 0;

  // Scale size based on number of dependents (max +10)
  return baseSize + Math.min(dependentCount * 2, 10);
}

/**
 * Filter graph by classification
 * @param {Object} graphData - Graph data
 * @param {string} filter - Filter type: 'all', 'applications', 'libraries'
 * @returns {Object} Filtered graph
 */
export function filterGraphByClassification(graphData, filter) {
  if (filter === 'all') {
    return graphData;
  }

  const classification = filter === 'applications' ? 'application' : 'library';
  const filteredNodes = graphData.nodes.filter(n => n.classification === classification);
  const nodeIds = new Set(filteredNodes.map(n => n.id));

  const filteredEdges = graphData.edges.filter(e =>
    nodeIds.has(e.source || e.from) && nodeIds.has(e.target || e.to)
  );

  return {
    nodes: filteredNodes,
    edges: filteredEdges
  };
}
