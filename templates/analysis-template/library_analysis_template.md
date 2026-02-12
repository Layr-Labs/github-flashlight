<!--
LIBRARY ANALYSIS TEMPLATE
=========================
This template provides a comprehensive structure for analyzing individual libraries/packages within a codebase.

INSTRUCTIONS:
1. Replace all [PLACEHOLDER] values with actual data from your analysis
2. Remove sections that are not applicable to your library
3. Add additional components, flows, or examples as needed
4. Code examples should use the appropriate language syntax
5. Keep descriptions detailed but focused on implementation specifics

TERMINOLOGY NOTE:
- "Library" refers to a reusable code module without an executable entrypoint
- Libraries are imported/used by applications or other libraries
- This includes shared modules, utility packages, data models, etc.

PLACEHOLDERS GUIDE:
- [LIBRARY_NAME]: Name of the library being analyzed
- [ANALYZER_ID]: ID of the analyzer agent
- [ISO_8601_TIMESTAMP]: Timestamp in ISO 8601 format
- [LIBRARY_TYPE]: Type (e.g., rust-crate, npm-package, python-package)
- [language]: Programming language for code blocks
- Other placeholders are self-explanatory within context
-->

# [LIBRARY_NAME] Analysis

**Analyzed by**: [ANALYZER_ID]
**Timestamp**: [ISO_8601_TIMESTAMP]
**Library Type**: [LIBRARY_TYPE]
**Classification**: library
**Location**: [RELATIVE_PATH_FROM_REPO_ROOT]
**Version**: [VERSION]

## Architecture

[Provide 2-4 paragraphs describing the overall architecture of this library. Include:
- High-level organizational structure and design philosophy
- Main architectural components/modules and their relationships
- Key design patterns employed (factory, builder, strategy, etc.)
- Technology stack and frameworks used
- Any unique architectural decisions or constraints
- How the library is designed to be consumed by other code]

## Key Components

- **[ComponentName]** (`[relative/path/to/file.ext]`): [One-sentence summary of component's primary responsibility]. [2-3 sentences describing key functionality, important methods/functions with signatures, and how it interacts with other components. Include specific implementation details like algorithms used, patterns employed, or important configuration.]

- **[ComponentName]** (`[relative/path/to/file.ext]`): [One-sentence summary]. [Detailed description of functionality, key methods, interactions, and implementation specifics.]

- **[ComponentName]** (`[relative/path/to/file.ext]`): [One-sentence summary]. [Detailed description.]

[Continue listing all major components - typically 3-8 components depending on library complexity. Each should be a distinct module, class, or logical unit that plays a significant role.]

## Data Flows

### 1. [Primary Data Processing Flow]
[Describe how data flows through the library's main processing pipeline. Use arrow notation (→) to show the sequence. Start with input data/function calls and trace through transformations, validations, and outputs.]

### 2. [Secondary Flow Name]
[Detailed flow description with step-by-step component interactions]

### 3. [Additional Flow Name]
[Detailed flow description]

[Document 2-5 major data flows that represent the core functionality of the library. Focus on flows that would help someone understand how to use the library effectively.]

## Dependencies

### External Dependencies

- **[package-name]** ([VERSION]): [One-sentence description of what the package does]. [2-3 sentences describing key features, APIs, or capabilities provided]. [How this library uses it - specific functions, patterns, or integration points]. [Any notable configuration or usage details.]

- **[package-name]** ([VERSION]): [Description and usage details]

- **[package-name]** ([VERSION]): [Description and usage details]

[List all major external dependencies. Focus on direct dependencies that are critical to functionality.]

### Internal Dependencies

[Only include this section if this library depends on OTHER internal libraries in the codebase]

- **[internal-library-name]** (`[relative/path]`): [One-sentence description of what this internal library provides]. [2-3 sentences describing what is imported from it, how it's used, and why this dependency exists. Include specific types, functions, or configurations imported.]

- **[internal-library-name]** (`[relative/path]`): [Description and usage details]

[List all internal dependencies on other libraries within the same codebase. These represent architectural relationships between different libraries.]

## API Surface

[This section documents the public interface of the library - what it exposes to applications and other libraries.]

### Public Functions

#### `[function_name]`

**Signature**:
```[language]
[full function signature with types]
```

**Purpose**: [Brief description of what this function does]

**Parameters**:
- `[param_name]` ([TYPE]): [Description of parameter]
- `[param_name]` ([TYPE]): [Description of parameter]

**Returns**: `[RETURN_TYPE]` - [Description of return value]

**Example Usage**:
```[language]
[code example showing typical usage]
```

**Notes**: [Any important notes about behavior, edge cases, error conditions]

---

#### `[function_name]`

[Repeat structure for other key public functions]

---

### Public Types/Structs/Classes

#### `[TypeName]`

```[language]
[full type/struct/class definition]
```

**Purpose**: [Description of what this type represents]

**Fields/Properties**:
- `[field_name]` ([TYPE]): [Description]
- `[field_name]` ([TYPE]): [Description]

**Methods**:
- `[method_name]([params])`: [Description]
- `[method_name]([params])`: [Description]

**Example Usage**:
```[language]
[code example showing how to create and use this type]
```

---

#### `[TypeName]`

[Repeat for other key public types]

---

### Public Traits/Interfaces (if applicable)

#### `[TraitName]`

```[language]
[trait/interface definition]
```

**Purpose**: [Description of what this trait/interface represents]

**Required Methods**:
- `[method_name]([params])`: [Description]
- `[method_name]([params])`: [Description]

**Example Implementation**:
```[language]
[code example showing an implementation]
```

---

### Public Constants/Enums (if applicable)

[Document important public constants or enums that consumers need to know about]

## Usage Patterns

### Pattern 1: [Common Usage Pattern Name]

**Use Case**: [When/why would someone use this pattern]

**Example**:
```[language]
[code example showing the pattern]
```

**Explanation**: [Step-by-step explanation of what's happening]

---

### Pattern 2: [Another Usage Pattern]

[Repeat structure for other common patterns]

---

## Code Examples

### Example 1: [Basic Usage Scenario]

**Scenario**: [Description of what this example demonstrates]

```[language]
[complete, runnable code example]
```

**Output/Result**:
```
[expected output or result]
```

**Explanation**: [Brief explanation of key points in the example]

---

### Example 2: [Advanced Usage Scenario]

[Repeat structure for additional examples - typically 2-4 examples covering basic to advanced usage]

---

## Testing

### Test Coverage

- **Unit tests**: [X]% coverage ([Y] test cases)
- **Integration tests**: [X]% coverage ([Y] test cases)
- **Test files**: `[path/to/tests]`

### Key Test Patterns

```[language]
[example of a typical test case showing how the library is tested]
```

[Describe the testing approach, any test utilities provided, and how consumers can test their own code that uses this library]

## Performance Characteristics

[Document any performance considerations, benchmarks, or optimization notes]

- **Time Complexity**: [For key operations, e.g., "O(n log n) for sorting operations"]
- **Space Complexity**: [Memory usage characteristics]
- **Benchmarks**: [Any benchmark results or performance metrics]
- **Optimization Notes**: [Any important performance considerations for users]

## Error Handling

[Describe the library's error handling approach]

**Error Types**:
- `[ErrorType]`: [When this error occurs and how to handle it]
- `[ErrorType]`: [Description]

**Example Error Handling**:
```[language]
[code example showing proper error handling when using the library]
```

## Consumed By

[List which applications or other libraries in the codebase use this library]

### Applications
- **[application-name]**: [How it uses this library, which APIs/features it relies on]
- **[application-name]**: [Description]

### Other Libraries
- **[library-name]**: [How it uses this library]
- **[library-name]**: [Description]

## Migration Notes (if applicable)

[Include this section if there were recent breaking changes or version upgrades]

### Recent Changes ([OLD_VERSION] → [NEW_VERSION])

**Breaking Changes**:
1. [Change description and migration path]
2. [Change description and migration path]

**New Features**:
- [Feature description]
- [Feature description]

**Deprecations**:
- [Deprecated API and replacement]

## Design Decisions

[Document important design decisions and their rationale]

### Decision 1: [Decision Title]

**Context**: [What problem was being solved]

**Decision**: [What was decided]

**Rationale**: [Why this decision was made, alternatives considered]

**Consequences**: [Trade-offs, implications]

---

### Decision 2: [Decision Title]

[Repeat structure for other significant design decisions]

---

## Future Improvements

[List potential improvements or known limitations]

1. **[Improvement Title]**: [Description of potential enhancement]
   - **Benefit**: [What would be gained]
   - **Effort**: [Estimated complexity]

2. **[Improvement Title]**: [Description]

## Related Documentation

- [Internal Documentation Title]([relative-path])
- [Related Library Analysis]([relative-path])
- [Architecture Documentation]([relative-path])
- [Official Package Documentation]([URL]) (if applicable for external dependencies)

## Files Analyzed

[List the key files that were analyzed to create this documentation]

- `[relative/path/to/file.ext]` - [Brief description of file's role]
- `[relative/path/to/file.ext]` - [Brief description]
- `[relative/path/to/file.ext]` - [Brief description]

[Include 5-20 files that represent the core of the library]

## Analysis Summary

**Analysis Depth**: [light | medium | deep]

**Overall Assessment**: [2-3 sentence summary of the library's design quality, role in the codebase, and general observations]

**Key Strengths**:
- [Strength 1]
- [Strength 2]
- [Strength 3]

**Areas for Improvement**:
- [Improvement area 1]
- [Improvement area 2]

**Recommendation**: [Brief recommendation for how the library should be used or maintained going forward]
