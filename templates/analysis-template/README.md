# Analysis Templates

This directory contains comprehensive markdown templates used by the code analysis agents to generate structured, detailed documentation for applications and packages/libraries.

## Templates

### 1. application_analysis_template.md
Used for analyzing **applications** - executable components with entrypoints and business purposes:
- Web servers, APIs, microservices
- CLI tools, command-line applications
- Background workers, daemons, agents
- Batch processors, ETL scripts

### 2. package_analysis_template.md
Used for analyzing **packages/libraries** - reusable code modules without entrypoints:
- Utility libraries (common-utils, helpers)
- Data models and schemas
- Shared business logic
- Framework extensions

## How Templates Are Used

### 1. Template Loading (agent/agent.py)
```python
templates_dir = Path(__file__).parent.parent / "templates" / "analysis-template"
template_loader = TemplateLoader(templates_dir)

# Templates are loaded and injected into code analyzer prompt
application_template = template_loader.get_template("application")
package_template = template_loader.get_template("package")
```

### 2. Template Injection (agent/utils/template_loader.py)
The `TemplateLoader` class:
- Loads both template files at initialization
- Provides instructions for template usage
- Injects templates into the code analyzer agent's prompt context
- Templates become available as `<application_analysis_template>` and `<package_analysis_template>`

### 3. Code Analyzer Usage (agent/prompts/code_analyzer.txt)
The code analyzer agent:
- Receives templates in its system prompt
- Selects appropriate template based on component classification
- Replaces all `[PLACEHOLDER]` values with actual analysis data
- Removes HTML comment instructions
- Fills in all sections with discovered information
- Generates comprehensive markdown documentation

### 4. Output Generation
Agents generate analysis files following template structure:
```
files/service_analyses/
├── component-name.json          # Structured data
├── component-name.md            # Generated from template
└── component-name_openapi.yaml  # API documentation (if applicable)
```

## Template Structure

Both templates include:

### Header Section
- Metadata (Analyzer ID, Timestamp, Classification, Type, Location)
- HTML comments with usage instructions (removed in output)

### Core Sections
1. **Architecture** - Overall design patterns, technology stack, execution model
2. **Key Components** - Major modules/classes with file paths and descriptions
3. **Data Flows / System Flows** - Step-by-step component interactions
4. **Dependencies** - External and internal dependencies with usage details
5. **API Surface** - Public interfaces (HTTP endpoints, functions, CLI commands)
6. **Code Examples** - Illustrative code snippets showing key patterns
7. **Files Analyzed** - List of examined files
8. **Analysis Notes** - Security, performance, scalability, improvements

### Application-Specific Sections
- **System Flows** - End-to-end request/response flows
- **Application Interactions** - How this app communicates with other apps
- **Libraries Used** - Internal library dependencies

### Package-Specific Sections
- **Usage Across Services** - Which applications/libraries use this package
- **Common Usage Patterns** - How the package is typically used
- **Features Used** - Which features are most commonly utilized
- **Integration Patterns** - How it integrates with other systems

## Placeholder Conventions

Templates use bracket notation for values to be replaced:

- `[APPLICATION_NAME]` / `[PACKAGE_NAME]` - Component name
- `[ANALYZER_ID]` - Agent identifier (e.g., "code-analyzer-api")
- `[ISO_8601_TIMESTAMP]` - ISO 8601 timestamp
- `[APPLICATION_TYPE]` / `[PACKAGE_TYPE]` - Component type (rust-crate, npm-package, etc.)
- `[CLASSIFICATION]` - library, service, cli-tool, worker, etc.
- `[RELATIVE_PATH_FROM_REPO_ROOT]` - Path from repo root
- `[VERSION]` - Version from manifest file
- `[language]` - Programming language (rust, typescript, python, go, etc.)
- `[X]`, `[Y]`, `[NUMBER]` - Numeric values
- `[ComponentName]` - Component names
- `[file/path]` - File paths

## Modifying Templates

When updating templates:

1. **Preserve Structure** - Keep section hierarchy and markdown formatting
2. **Update Instructions** - Modify HTML comments to guide agents
3. **Test with Agents** - Run analysis to verify templates work correctly
4. **Version Control** - Document significant template changes
5. **Consistency** - Keep both templates structurally similar where applicable

## Quality Standards

Templates enforce quality standards for analysis output:

- **Architecture**: 2-4 detailed paragraphs
- **Key Components**: 5-12 components with file paths and descriptions
- **Data Flows**: 3-7 major flows with step-by-step interactions
- **Dependencies**: All major deps with versions and usage details
- **Code Examples**: 3-6 examples showing key patterns
- **Analysis Notes**: Security, performance, scalability observations

## Integration Points

### 1. Code Analyzer Agent
- Receives templates in system prompt
- Uses template structure for markdown generation
- Fills placeholders with analysis data

### 2. Website Generator
- Reads markdown files generated from templates
- Parses structured sections for web display
- Expects consistent section names and formatting

### 3. Architecture Documenter
- Reads all component analyses
- Synthesizes findings across components
- Expects consistent data structure

## Example Usage

When the code analyzer analyzes a component:

```
1. Determine classification: Application or Library
2. Select appropriate template
3. Read entire template including HTML comments
4. Explore codebase using Glob, Grep, Read, Bash
5. Replace all [PLACEHOLDER] values with actual data
6. Remove HTML comments and inapplicable sections
7. Add additional content beyond template minimums
8. Write comprehensive markdown to files/service_analyses/
```

## Troubleshooting

**Templates not loading:**
- Check file names match exactly: `application_analysis_template.md`, `package_analysis_template.md`
- Verify files are in `templates/analysis-template/` directory
- Check file permissions and encoding (UTF-8)

**Incomplete analysis output:**
- Agents may skip sections if not enough information
- Some sections marked "if applicable" can be removed
- Check agent logs for errors during analysis

**Inconsistent formatting:**
- Verify placeholders were replaced correctly
- Check code blocks have language specified
- Ensure HTML comments were removed

## Future Enhancements

Potential improvements to template system:

- [ ] Add templates for specific languages (Rust-specific, Go-specific, etc.)
- [ ] Template versioning system
- [ ] Validation tool to check generated output against template structure
- [ ] Additional templates for specialized component types (workers, CLIs, etc.)
- [ ] Template customization per project
