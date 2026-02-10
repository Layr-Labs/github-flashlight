"""Loads and manages markdown templates for code analysis."""

from pathlib import Path
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class TemplateLoader:
    """Loads and manages markdown templates for code analysis."""

    def __init__(self, templates_dir: Path):
        self.templates_dir = Path(templates_dir)
        self._templates: Dict[str, str] = {}
        self._load_templates()

    def _load_templates(self):
        """Load all template files from templates directory."""
        application_template = self.templates_dir / "application_analysis_template.md"
        package_template = self.templates_dir / "package_analysis_template.md"

        if application_template.exists():
            self._templates['application'] = application_template.read_text(encoding='utf-8')
            logger.info(f"Loaded application template from {application_template}")
        else:
            logger.warning(f"Application template not found at {application_template}")

        if package_template.exists():
            self._templates['package'] = package_template.read_text(encoding='utf-8')
            logger.info(f"Loaded package template from {package_template}")
        else:
            logger.warning(f"Package template not found at {package_template}")

    def get_template(self, template_type: str) -> str:
        """
        Get template content by type.

        Args:
            template_type: Either 'application' or 'package'

        Returns:
            Template content string, or empty string if not found
        """
        return self._templates.get(template_type, "")

    def get_template_instructions(self) -> str:
        """
        Generate instructions for using templates.

        Returns:
            Instructions text to be included in agent prompt
        """
        return """
# MARKDOWN TEMPLATE USAGE INSTRUCTIONS

When writing markdown analysis, you MUST use the templates provided below in your context.

## Template Selection

- **For APPLICATIONS/SERVICES**: Use the <application_analysis_template>
- **For LIBRARIES/PACKAGES**: Use the <package_analysis_template>

## Template Structure

The templates contain:
- Structured sections with clear headings (Architecture, Key Components, Dependencies, etc.)
- Placeholder values marked with **[BRACKETS]** - you MUST replace ALL placeholders
- HTML comments with instructions - read them carefully but don't include in output
- Example formats for code blocks, lists, and tables

## Critical Requirements

1. **Replace ALL [PLACEHOLDER] values** with actual analysis data from your code exploration
2. **Remove HTML comment instructions** - they're for guidance only
3. **Remove sections marked "if applicable"** if they don't apply to this component
4. **Add additional content** - templates show minimum structure, add more components/flows as needed
5. **Use specific language names** in code blocks (rust, typescript, python, etc. - not [language])
6. **Keep descriptions detailed** with specific implementation details, not generic summaries

## Placeholder Mapping Examples

- `[APPLICATION_NAME]` / `[PACKAGE_NAME]` → Use actual component name from analysis
- `[ANALYZER_ID]` → Use your agent identifier (e.g., "code-analyzer-api")
- `[ISO_8601_TIMESTAMP]` → Use current timestamp in ISO 8601 format
- `[APPLICATION_TYPE]` / `[PACKAGE_TYPE]` → Component type (rust-crate, npm-package, python-package, etc.)
- `[CLASSIFICATION]` → library, service, cli-tool, worker, api-gateway, etc.
- `[RELATIVE_PATH_FROM_REPO_ROOT]` → Path from repository root to component
- `[VERSION]` → Extract from Cargo.toml, package.json, or other manifest
- `[language]` → Actual language (rust, javascript, typescript, python, go, etc.)

## Code Block Formatting

Always specify the language for syntax highlighting:

````markdown
```rust
// Example Rust code
pub struct MyStruct { }
```
````

Not:
````markdown
```[language]
// Code here
```
````

## Quality Standards

- Architecture section: 2-4 detailed paragraphs about design patterns, technology stack, execution model
- Key Components: List 5-12 major components with file paths and detailed descriptions
- Data Flows: Document 3-7 major flows with step-by-step component interactions
- Dependencies: List all major external dependencies with versions and usage details
- API Surface: Document all public interfaces (HTTP endpoints, exported functions, CLI commands)
- Code Examples: Include 3-6 examples showing key patterns or complex implementations
- Analysis Notes: Provide security, performance, scalability observations and improvement suggestions

The templates are comprehensive guides - follow their structure but expand with all relevant details you discover during analysis.
"""
