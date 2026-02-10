# Testing the Multi-Agent Analysis System

This example project is designed to test the codebase analysis system with minimal code.

## What This Tests

### Service Discovery
- Should discover 3 services: `api`, `auth`, `database`
- Should discover 1 library: `common`

### Dependency Analysis
- **External Dependencies**: express, axios, jsonwebtoken, body-parser
- **Internal Dependencies**:
  - All services depend on `@task-manager/common`
  - API service depends on auth and database services (runtime HTTP calls)

### Architecture Patterns
- Microservices architecture
- Service-to-service communication via HTTP/REST
- Shared library for common utilities
- JWT-based authentication
- Middleware pattern (authentication middleware)

### API Surface Documentation
- **Auth Service**: 2 endpoints (login, verify)
- **Database Service**: 4 endpoints (get, post, delete, list)
- **API Service**: 5 endpoints (CRUD operations for tasks)

### Data Flows
Should identify flows like:
1. Task Creation Flow: API → Auth (verify) → Database (store)
2. Login Flow: API → Auth (login) → JWT generation
3. Task Retrieval Flow: API → Auth (verify) → Database (get) → Filter by user

### Code Quality
- TypeScript with proper types
- Error handling patterns
- Logging with shared logger
- Input validation
- Authentication/authorization

## Expected Analysis Output

### Applications (3)
1. **api-service** (TypeScript/Node.js)
   - Classification: application
   - Type: node-service
   - 5 HTTP endpoints
   - Depends on: auth-service, database-service, common library

2. **auth-service** (TypeScript/Node.js)
   - Classification: application
   - Type: node-service
   - 2 HTTP endpoints
   - Depends on: common library

3. **database-service** (TypeScript/Node.js)
   - Classification: application
   - Type: node-service
   - 4 HTTP endpoints
   - Depends on: common library

### Libraries (1)
1. **common** (TypeScript)
   - Classification: library
   - Type: typescript-library
   - Exports: Logger, Validator, ValidationError, LogLevel
   - Used by: all 3 services

## Running the Analysis

```bash
# From the flashlight directory
python -m agent.agent

# Enter the path when prompted:
/Users/ethen/github-flashlight/test-examples/task-manager

# The system should:
# 1. Discover 4 components (3 apps + 1 library)
# 2. Analyze dependencies (external + internal)
# 3. Generate markdown documentation for each component
# 4. Create dependency graph JSON
# 5. Generate architecture documentation
# 6. Build interactive website
```

## Validation Checklist

After running the analysis, verify:

- [ ] 4 markdown files generated in `files/service_analyses/`
  - [ ] api.md
  - [ ] auth.md
  - [ ] database.md
  - [ ] common.md

- [ ] Each markdown file contains:
  - [ ] Component classification (application vs library)
  - [ ] Component type (node-service or typescript-library)
  - [ ] Architecture section
  - [ ] Key Components section
  - [ ] Dependencies section (external + internal)
  - [ ] API Surface section (for services with HTTP endpoints)
  - [ ] Code Examples section

- [ ] Dependency graph JSON generated:
  - [ ] Nodes for all 4 components
  - [ ] Edges showing dependencies (services → common)

- [ ] Architecture documentation:
  - [ ] Overall system architecture
  - [ ] Service interaction patterns
  - [ ] Technology stack

- [ ] Website generated:
  - [ ] Component list with 4 items
  - [ ] Each component shows full markdown documentation
  - [ ] Dependency graph visualization
  - [ ] API documentation prettified

## Token Efficiency

This example is intentionally minimal:
- **3 services** × ~100 lines = ~300 lines of service code
- **1 library** × ~50 lines = ~50 lines of library code
- **Total**: ~350 lines of actual code

Should consume approximately:
- Discovery: ~1K tokens
- Analysis per component: ~5-10K tokens
- Total analysis: ~25-40K tokens
- Website generation: ~5K tokens
- **Grand total**: ~30-45K tokens (well under limits)

## Example API Calls

Test the application with these curl commands:

```bash
# Login
curl -X POST http://localhost:3001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Create task (replace TOKEN)
curl -X POST http://localhost:3000/tasks \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test Task","description":"Test description"}'

# List tasks
curl http://localhost:3000/tasks \
  -H "Authorization: Bearer TOKEN"
```
