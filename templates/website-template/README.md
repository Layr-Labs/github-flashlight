# Code Analysis Viewer

Interactive React SPA for exploring codebase analysis with integrated Swagger documentation.

## Features

- 🗺️ **Interactive Dependency Graph** - D3.js visualization with zoom, pan, and click-to-navigate
- 🔍 **Searchable Service Catalog** - Filter by application/library, search by name
- 📖 **Integrated Swagger UI** - Interactive API documentation for services with OpenAPI specs
- 🏗️ **Architecture Overview** - System-level documentation and insights
- 🎨 **Clean, Modern UI** - Responsive design with smooth animations

## Prerequisites

- Node.js 16+ and npm

## Installation

```bash
npm install
```

## Development

Start the development server:

```bash
npm start
```

Opens at [http://localhost:3000](http://localhost:3000)

## Production Build

Create an optimized production build:

```bash
npm run build
```

Creates static files in the `build/` directory.

## Deployment

The `build/` directory can be deployed to any static hosting service:

- **Vercel**: `vercel deploy`
- **Netlify**: Drag and drop `build/` folder
- **GitHub Pages**: Push `build/` to gh-pages branch
- **AWS S3**: Upload `build/` contents to S3 bucket

## Project Structure

```
├── public/
│   └── index.html          # HTML entry point
├── src/
│   ├── components/         # React components
│   │   ├── Header.jsx
│   │   ├── ArchitectureOverview.jsx
│   │   ├── ServiceList.jsx
│   │   ├── ServiceDetail.jsx
│   │   ├── SwaggerUI.jsx  # OpenAPI documentation viewer
│   │   └── DependencyGraph.jsx
│   ├── data/
│   │   └── analysisData.js # Consolidated analysis data (auto-generated)
│   ├── utils/
│   │   ├── graphLayout.js  # D3.js utilities
│   │   └── dataTransforms.js
│   ├── App.js
│   ├── index.js
│   └── index.css
├── package.json
└── README.md
```

## Data Structure

The application expects data in `src/data/analysisData.js` with this structure:

```javascript
{
  services: [{
    name: "service-name",
    classification: "application" | "library",
    type: "go-binary" | "rust-crate" | etc,
    description: "...",
    architecture: "...",
    key_components: [...],
    system_flows: [...],
    hasApiDocs: true,        // If OpenAPI spec available
    openApiSpec: {...}       // OpenAPI 3.0 spec object
  }],
  dependencyGraph: {
    nodes: [...],
    edges: [...]
  },
  architecture: {...}
}
```

## Customization

### Adding OpenAPI Specifications

To add API documentation for a service:

1. Include the OpenAPI spec in the service object:
   ```javascript
   {
     name: "my-service",
     hasApiDocs: true,
     openApiSpec: {
       openapi: "3.0.0",
       // ... your OpenAPI spec
     }
   }
   ```

2. The service will automatically show an "API Documentation" button
3. Navigate to `/services/{serviceName}/api` to view the Swagger UI

### Styling

Edit `src/index.css` to customize the color scheme and design. CSS variables are defined at the top:

```css
:root {
  --color-primary: #4F88FF;
  --color-secondary: #10B981;
  /* ... */
}
```

## Technologies

- **React 18** - UI framework
- **React Router** - Client-side routing
- **D3.js** - Interactive graph visualization
- **Swagger UI React** - OpenAPI documentation rendering
- **Create React App** - Build tooling

## License

MIT
