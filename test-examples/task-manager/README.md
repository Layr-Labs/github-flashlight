# Task Manager - Example CRUD Application

A minimal microservices application for testing codebase analysis tools.

## Architecture

This application demonstrates a simple 3-service architecture:

- **API Service** - REST API gateway for task management
- **Auth Service** - JWT-based authentication
- **Database Service** - In-memory data store

All services share a common library for utilities.

## Services

### API Service (Port 3000)
REST API exposing CRUD endpoints for tasks:
- `POST /tasks` - Create a task
- `GET /tasks` - List all tasks
- `GET /tasks/:id` - Get a task
- `PUT /tasks/:id` - Update a task
- `DELETE /tasks/:id` - Delete a task

Requires authentication via JWT token.

### Auth Service (Port 3001)
Handles user authentication:
- `POST /auth/login` - Login with username/password
- `POST /auth/verify` - Verify JWT token

### Database Service (Port 3002)
Simple key-value store:
- `GET /data/:key` - Get value
- `POST /data` - Store value
- `DELETE /data/:key` - Delete value

## Running

```bash
npm install
npm run start:auth
npm run start:db
npm run start:api
```

## Technology Stack

- Node.js + TypeScript
- Express.js for HTTP servers
- jsonwebtoken for authentication
- axios for inter-service communication
