/**
 * Consolidated analysis data
 *
 * This file is a TEMPLATE that will be populated by the website generator agent.
 * The generator will:
 * 1. Read all service analysis JSONs
 * 2. Read all OpenAPI spec YAML files
 * 3. Read dependency graphs
 * 4. Read architecture documentation
 * 5. Generate this file with actual data
 *
 * DO NOT EDIT MANUALLY - This file is auto-generated
 */

const analysisData = {
  // Array of all services (applications + libraries)
  services: [
    // Example structure - will be replaced with actual data
    {
      name: "example-service",
      classification: "application", // or "library"
      type: "go-binary", // or "rust-crate", "nodejs-package", etc.
      location: "/path/to/service",
      description: "Service description from analysis",
      architecture: "Detailed architecture description...",

      key_components: [
        "Component 1: Description",
        "Component 2: Description"
      ],

      system_flows: [
        "Flow 1: Step 1 → Step 2 → Step 3",
        "Flow 2: Description"
      ],

      external_dependencies: [
        "dependency1: Purpose",
        "dependency2: Purpose"
      ],

      libraries_used: [
        "library1: How it's used",
        "library2: Integration details"
      ],

      application_interactions: [
        {
          target: "other-service",
          type: "http_api", // or "grpc", "message_queue", "shared_database"
          description: "How they interact"
        }
      ],

      api_surface: "API description...",

      // OpenAPI spec (if available)
      hasApiDocs: true,
      openApiSpec: {
        openapi: "3.0.0",
        info: {
          title: "Example API",
          version: "1.0.0",
          description: "API description"
        },
        paths: {
          "/example": {
            get: {
              summary: "Example endpoint",
              responses: {
                "200": {
                  description: "Success"
                }
              }
            }
          }
        }
      }
    }
  ],

  // Dependency graph structure
  dependencyGraph: {
    graphType: "dependencies",
    nodes: [
      {
        id: "example-service",
        classification: "application",
        type: "go-binary",
        phase: 1
      }
    ],
    edges: [
      {
        from: "service-a",
        to: "service-b"
      }
    ]
  },

  // Architecture documentation
  architecture: {
    overview: "System architecture overview...",
    totalServices: 0,
    patterns: [
      "Pattern 1",
      "Pattern 2"
    ],
    techStack: {
      languages: ["Go", "Rust", "TypeScript"],
      frameworks: ["Framework1", "Framework2"],
      databases: ["PostgreSQL", "Redis"]
    }
  },

  // Metadata about the analysis
  metadata: {
    generatedAt: new Date().toISOString(),
    totalServices: 0,
    totalApplications: 0,
    totalLibraries: 0,
    servicesWithAPIs: 0
  }
};

export default analysisData;
