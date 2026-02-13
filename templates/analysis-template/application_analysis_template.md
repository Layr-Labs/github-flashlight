<!--
APPLICATION ANALYSIS TEMPLATE
==============================
This template provides a comprehensive structure for analyzing individual applications/services within a codebase.

INSTRUCTIONS:
1. Replace all [PLACEHOLDER] values with actual data from your analysis
2. Remove sections that are not applicable to your application
3. Add additional components, flows, or examples as needed
4. Code examples should use the appropriate language syntax
5. Keep descriptions detailed but focused on implementation specifics

TERMINOLOGY NOTE:
- "Application" is used instead of "service" to reflect updated system terminology
- An application can be a microservice, library, CLI tool, worker process, etc.

PLACEHOLDERS GUIDE:
- [APPLICATION_NAME]: Name of the application being analyzed
- [ANALYZER_ID]: ID of the analyzer agent
- [ISO_8601_TIMESTAMP]: Timestamp in ISO 8601 format
- [APPLICATION_TYPE]: Type/classification (e.g., rust-crate, npm-package, python-service)
- [language]: Programming language for code blocks
- Other placeholders are self-explanatory within context
-->

# [APPLICATION_NAME] Analysis

**Analyzed by**: [ANALYZER_ID]
**Timestamp**: [ISO_8601_TIMESTAMP]
**Application Type**: [APPLICATION_TYPE]
**Classification**: [library | service | cli-tool | worker | api-gateway | etc.]
**Location**: [RELATIVE_PATH_FROM_REPO_ROOT]

## Architecture

[Provide 2-4 paragraphs describing the overall architecture of this application. Include:
- High-level architectural pattern (layered, hexagonal, event-driven, etc.)
- Main architectural components and their relationships
- Key design patterns employed (middleware, repository, factory, etc.)
- Technology stack and frameworks used
- Execution model (synchronous, asynchronous, event-driven, etc.)
- Error handling approach
- Any unique architectural decisions or constraints]

## Key Components

- **[ComponentName]** (`[relative/path/to/file.ext]`): [One-sentence summary of component's primary responsibility]. [2-3 sentences describing key functionality, important methods/functions with signatures, and how it interacts with other components. Include specific implementation details like algorithms used, patterns employed, or important configuration.]

- **[ComponentName]** (`[relative/path/to/file.ext]`): [One-sentence summary]. [Detailed description of functionality, key methods, interactions, and implementation specifics.]

- **[ComponentName]** (`[relative/path/to/file.ext]`): [One-sentence summary]. [Detailed description.]

[Continue listing all major components - typically 5-12 components depending on application complexity. Each should be a distinct module, class, or logical unit that plays a significant role.]

## Data Flows

[Document 3-7 major data flows that represent the core functionality of the application. For EACH flow, provide both a visual mermaid diagram and detailed textual description. Focus on the most important or complex flows that would help someone understand how the application works.]

### 1. [Primary Flow Name]

**Flow Description**: [One-sentence summary of what this flow accomplishes and when it's triggered]

```mermaid
sequenceDiagram
    participant [Component1]
    participant [Component2]
    participant [Component3]
    participant [ExternalSystem]

    [Component1]->>>[Component2]: [method_call(params)]<br/>[Brief data description]
    Note over [Component2]: [Processing step description]
    [Component2]->>>[Component3]: [method_call(data)]<br/>[Data transformation]
    [Component3]->>>[ExternalSystem]: [API call or operation]<br/>[Request format]
    [ExternalSystem]--->>>[Component3]: [Response data]
    [Component3]--->>>[Component2]: [Processed result]
    [Component2]--->>>[Component1]: [Final output]

    Note over [Component1],[Component3]: [Additional context about the flow]
```

**Detailed Steps**:

1. **[Step Description]** ([Component1] → [Component2])
   - Method: `[method_name(param1: Type, param2: Type)]`
   - Input: [Description of input data structure]
   - Processing: [What happens in this step]

2. **[Step Description]** ([Component2] → [Component3])
   - Method: `[method_name()]`
   - Transformation: [How data is transformed]
   - Output: [Result data structure]

3. **[Step Description]** ([Component3] → [ExternalSystem])
   - Operation: [Description of external interaction]
   - Protocol: [HTTP, gRPC, database query, etc.]
   - Format: [Data format used]

[Continue for all steps in the flow]

**Error Paths**:
- **[Error Condition]** → [How it's detected and handled, including error codes/responses]
- **[Error Condition]** → [Recovery mechanism or error propagation]

**Key Technical Details**:
- Data formats: [JSON, protobuf, binary, etc.]
- Protocols: [HTTP/1.1, gRPC, WebSocket, etc.]
- Transaction handling: [If applicable]
- Performance characteristics: [Latency, throughput considerations]

---

### 2. [Secondary Flow Name]

**Flow Description**: [One-sentence summary]

```mermaid
sequenceDiagram
    participant [Component1]
    participant [Component2]
    participant [Database]

    [Component1]->>>[Component2]: [operation(data)]
    [Component2]->>>[Database]: [SQL query or operation]
    [Database]--->>>[Component2]: [Result set]
    [Component2]--->>>[Component1]: [Processed data]

    alt [Condition Name]
        [Component2]->>>[Component2]: [Alternative processing]
    else [Condition Name]
        [Component2]->>>[Database]: [Different operation]
    end
```

**Detailed Steps**:

[Follow same format as Flow 1]

**Error Paths**:
[Error handling details]

---

### 3. [Additional Flow Name]

**Flow Description**: [One-sentence summary]

```mermaid
sequenceDiagram
    participant [EntryPoint]
    participant [ProcessorA]
    participant [ProcessorB]
    participant [Output]

    [EntryPoint]->>>[ProcessorA]: [Initial data]
    loop [Loop description]
        [ProcessorA]->>>[ProcessorB]: [Batch of items]
        [ProcessorB]--->>>[ProcessorA]: [Processing results]
    end
    [ProcessorA]->>>[Output]: [Final aggregated result]
```

**Detailed Steps**:

[Follow same format]

**Used By**: [List which components, endpoints, or other flows depend on this flow]

---

[Continue documenting remaining major flows using the same format]

### Mermaid Diagram Guidelines

When creating sequence diagrams:
- Use descriptive participant names matching actual component names
- Include method/function names in arrows when relevant
- Add brief data descriptions in `<br/>` tags for clarity
- Use `Note over` for processing steps or important context
- Use `alt`/`else` blocks for conditional flows
- Use `loop` blocks for iterations
- Use solid arrows (`->>>`) for synchronous calls
- Use dashed arrows (`--->>>`) for responses/returns
- Keep diagrams focused on one flow - don't try to show everything

## Dependencies

### External Applications

- **[package-name]** ([VERSION]): [One-sentence description of what the package does]. [2-3 sentences describing key features, APIs, or capabilities provided]. [How this application uses it - specific functions, patterns, or integration points]. [Any notable configuration or usage details like performance characteristics, feature flags, etc.]

- **[package-name]** ([VERSION]): [Description and usage details]

- **[package-name]** ([VERSION]): [Description and usage details]

[List all major external applications - typically 5-15 packages depending on application complexity. Focus on direct applications that are critical to functionality.]

### Internal Aplications

- **[internal-module-name]** (`[relative/path]`): [One-sentence description of what this internal dependency provides]. [2-3 sentences describing what is imported from it, how it's used, and why this dependency exists. Include specific types, functions, or configurations imported.]

- **[internal-module-name]** (`[relative/path]`): [Description and usage details]

- **[internal-module-name]** (`[relative/path]`): [Description and usage details]

[List all internal dependencies on other applications or shared modules within the same codebase. These represent architectural relationships between different parts of the system.]

## API Surface

[Note: This section documents the public interface of the application - what it exposes to other applications or external consumers. Remove subsections that don't apply to your application type.]

### HTTP Endpoints

[If this is a web service/API, document all HTTP endpoints]

#### [METHOD] /path/to/endpoint
**Summary**: [Brief one-sentence description of what this endpoint does]
**Request Body** (if applicable):
```json
{
  "field_name": "type (validation rules)",
  "another_field": "type (constraints)"
}
```
**Success Response** ([STATUS_CODE] [Status Name]):
```json
{
  "response_field": "type",
  "nested": {
    "field": "value"
  }
}
```
**Error Responses**:
- [STATUS_CODE] [Status Name]: [Description of when this occurs]
- [STATUS_CODE] [Status Name]: [Description]

[Repeat for each endpoint - typically 3-20 endpoints depending on application]

### Exported Libraries/Modules

[If this application exports code for use by other applications]

**[ExportedComponent]**: [Description of what's exported and how to import it]
```[language]
// Usage example in other applications
[code showing how to import and use]
```
**Functionality**: [Description of what this provides to consumers]

### Exported Types/Interfaces

[If this application exports types, interfaces, or data structures]

- **[TypeName]**: [Description]
  ```[language]
  [type/interface definition]
  ```

- **[TypeName]**: [Description]

### CLI Commands

[If this is a CLI tool, document available commands]

#### [command-name] [arguments]
**Description**: [What this command does]
**Arguments**:
- `[arg-name]`: [type] - [description]
- `[--flag]`: [description]

**Example**:
```bash
[example command usage]
```

### Message/Event Interface

[If this application consumes or produces messages/events]

#### Published Events
- **[EventName]**: [When this event is published and what data it contains]

#### Consumed Events
- **[EventName]**: [What events this application listens for and how it responds]

### API Documentation Links

[If external API documentation exists, link to it]
- [API Documentation Title]([relative-path-or-url])
- [OpenAPI/Swagger Specification]([path])

## Code Examples

[Provide 3-6 code examples that illustrate key functionality, important patterns, or complex implementations within this application. Each example should be self-contained and well-commented.]

### Example 1: [Descriptive Title of What This Example Shows]

```[language]
// [relative/path/to/file.ext]
[Code example with inline comments explaining key points]
```

### Example 2: [Descriptive Title]

```[language]
// [relative/path/to/file.ext]
[Code example demonstrating important pattern or functionality]
```

### Example 3: [Descriptive Title]

```[language]
// [relative/path/to/file.ext]
[Code example]
```

[Add more examples as needed to cover the most important or complex aspects of the application]

## Files Analyzed

- `[relative/path/to/file.ext]` ([X] lines) - [Brief description of file's purpose]
- `[relative/path/to/file.ext]` ([X] lines) - [Description]
- `[relative/path/to/file.ext]` ([X] lines) - [Description]

[List all significant files that were analyzed to create this document. Include configuration files, main source files, tests, and documentation. This provides traceability and helps readers understand the scope of analysis.]

## Analysis Notes

[This section provides insights, observations, and recommendations based on the analysis]

### Security Considerations

1. **[Security Aspect]**: [Description of current implementation and security implications]. [Recommendations or observations about security posture].

2. **[Security Aspect]**: [Description and recommendations]

3. **[Security Aspect]**: [Description and recommendations]

[Document 3-7 security considerations relevant to this application. Consider authentication, authorization, data protection, input validation, dependency vulnerabilities, etc.]

### Performance Characteristics

- **[Performance Aspect]**: [Measurement or observation about performance]. [Context about acceptability or recommendations for optimization].
- **[Performance Aspect]**: [Description and implications]
- **[Performance Aspect]**: [Description and implications]

[Document key performance characteristics including benchmarks, bottlenecks, resource usage, or scaling behavior observed in the code]

### Scalability Notes

- **[Scalability Factor]**: [Description of how this application scales or factors that limit scaling]
- **[Scalability Factor]**: [Description and implications]
- **[Scalability Factor]**: [Description and implications]

[Discuss horizontal/vertical scaling capabilities, stateful vs stateless design, potential bottlenecks, and architectural considerations for growth]
