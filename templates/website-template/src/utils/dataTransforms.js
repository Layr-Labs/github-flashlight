/**
 * Utility functions for transforming analysis data
 */

/**
 * Parse YAML OpenAPI spec (if stored as string)
 * @param {string} yamlString - YAML content
 * @returns {Object} Parsed OpenAPI spec
 */
export function parseYAML(yamlString) {
  // This would use js-yaml library if needed
  // For now, assume specs are pre-parsed objects
  return typeof yamlString === 'string' ? JSON.parse(yamlString) : yamlString;
}

/**
 * Enrich service data with OpenAPI specs
 * @param {Array} services - Service analysis data
 * @param {Array} openApiSpecs - OpenAPI specifications
 * @returns {Array} Enriched services
 */
export function enrichServicesWithAPISpecs(services, openApiSpecs) {
  return services.map(service => {
    const spec = openApiSpecs.find(s =>
      s.name === service.name || s.name === `${service.name}_openapi`
    );

    return {
      ...service,
      hasApiDocs: !!spec,
      openApiSpec: spec?.spec || null
    };
  });
}

/**
 * Extract unique technologies from services
 * @param {Array} services - Service analysis data
 * @returns {Array} Unique technology names
 */
export function extractTechnologies(services) {
  const techSet = new Set();

  services.forEach(service => {
    if (service.type) {
      techSet.add(service.type);
    }
    if (service.techStack) {
      service.techStack.forEach(tech => techSet.add(tech));
    }
  });

  return Array.from(techSet).sort();
}

/**
 * Group services by classification
 * @param {Array} services - Service analysis data
 * @returns {Object} Grouped services
 */
export function groupServicesByClassification(services) {
  return {
    applications: services.filter(s => s.classification === 'application'),
    libraries: services.filter(s => s.classification === 'library')
  };
}

/**
 * Calculate dependency statistics
 * @param {Object} dependencyGraph - Dependency graph data
 * @returns {Object} Statistics
 */
export function calculateDependencyStats(dependencyGraph) {
  const { nodes = [], edges = [] } = dependencyGraph;

  return {
    totalNodes: nodes.length,
    totalEdges: edges.length,
    applications: nodes.filter(n => n.classification === 'application').length,
    libraries: nodes.filter(n => n.classification === 'library').length,
    phase1: nodes.filter(n => n.phase === 1).length,
    phase2Plus: nodes.filter(n => n.phase !== 1).length
  };
}
