<!--
PACKAGE ANALYSIS TEMPLATE
========================
This template provides a comprehensive structure for analyzing package/library usage across a codebase.

INSTRUCTIONS:
1. Replace all [PLACEHOLDER] values with actual data from your analysis
2. Remove sections that are not applicable to your package
3. Add additional pattern sections as needed
4. Code examples should use the appropriate language syntax
5. Keep descriptions concise but informative

PLACEHOLDERS GUIDE:
- [PACKAGE_NAME]: Name of the package being analyzed
- [VERSION]: Version number (e.g., 4.4.0)
- [ANALYZER_ID]: ID of the analyzer agent
- [ISO_8601_TIMESTAMP]: Timestamp in ISO 8601 format
- [language]: Programming language for code blocks
- [X], [Y], [NUMBER]: Numeric values from analysis
- Other placeholders are self-explanatory within context
-->

# Package Analysis: [PACKAGE_NAME]

**Analyzed by**: [ANALYZER_ID]
**Timestamp**: [ISO_8601_TIMESTAMP]
**Package Name**: [PACKAGE_NAME]
**Version**: [VERSION]
**Package Type**: [external-dependency | internal-library | shared-module | etc.]
**Language/Ecosystem**: [LANGUAGE] ([PACKAGE_REGISTRY])
**License**: [LICENSE_TYPE]

## Overview

[Provide a 2-3 sentence description of what this package does and its primary purpose. Then explain how it's used across the codebase and its role in the overall architecture.]

## Usage Across Services

### Services Using This Package

1. **[service-name]** ([Usage level: Primary/Heavy/Moderate/Light] consumer)
   - Usage: [Brief description of how this service uses the package]
   - [Relevant metrics: endpoints/functions/classes/etc.]: [NUMBER]
   - Features used: [List key features or APIs used]
   - Version: [VERSION]

2. **[service-name]** ([Usage level] consumer)
   - Usage: [Brief description]
   - [Relevant metrics]: [NUMBER]
   - Features used: [List key features]
   - Version: [VERSION]

[Repeat for each service using this package]

### Dependency Statistics

- **Total services using this package**: [X] out of [Y] services
- **Total files importing this package**: [NUMBER] files
- **Most common imports**: `[import statements or usage patterns]`
- **[Other relevant metric]**: [VALUE]

## Common Usage Patterns

### Pattern 1: [Pattern Name/Description]

**Frequency**: Used in [X] services / [Y] times total
**Purpose**: [Brief explanation of what this pattern accomplishes]

```[language]
// [Description of the pattern]
[code example showing the pattern]
```

**Files using this pattern**:
- `[file-path]:[line-range]`
- `[file-path]:[line-range]`
- `[file-path]:[line-range]`

### Pattern 2: [Pattern Name/Description]

**Frequency**: [X] instances across [Y] services
**Purpose**: [Brief explanation]

```[language]
// [Description of the pattern]
[code example showing the pattern]
```

**Variations**:
- [Variation 1]: [Brief description] ([X] occurrences)
- [Variation 2]: [Brief description] ([X] occurrences)
- [Variation 3]: [Brief description] ([X] occurrences)

### Pattern 3: [Pattern Name/Description]

**Frequency**: [X] implementations/usages
**Purpose**: [Brief explanation]

```[language]
// [Description of the pattern]
[code example showing the pattern]
```

**[Sub-categorization if relevant]**:
- [Category 1]: [X] implementations ([locations])
- [Category 2]: [X] implementations ([locations])
- [Category 3]: [X] implementations ([locations])

[Repeat Pattern sections as needed for additional patterns discovered]

## Features Used

### Core Features

| Feature | Services Using | Usage Frequency | Purpose |
|---------|---------------|-----------------|---------|
| `[feature/API]` | [X] | [Y] times | [Brief description] |
| `[feature/API]` | [X] | [Y] times | [Brief description] |
| `[feature/API]` | [X] | [Y] times | [Brief description] |

### Advanced Features

| Feature | Services Using | Usage Count | Purpose |
|---------|---------------|-------------|---------|
| [Feature Name] | [X] | [Y] implementations/uses | [Brief description] |
| [Feature Name] | [X] | [Y] implementations/uses | [Brief description] |
| [Feature Name] | [X] | [Y] implementations/uses | [Brief description] |

### Package Features/Flags Enabled

```[config-format]
# [Description of configuration]
[package] = { version = "[VERSION]", features = ["[feature1]", "[feature2]"] }

# [service-name] enables additional features
[package] = { version = "[VERSION]", features = ["[feature1]", "[feature2]", "[feature3]"] }
```

**Feature usage**:
- `[feature-name]`: [Description] - Used by [X] services ([list])
- `[feature-name]`: [Description] - Used by [X] services ([list])
- `[feature-name]`: [Description] - Used by [X] services ([list])

## Integration Patterns

### With [Related Package/System 1]

[Brief description of how this package integrates with another system/package]

- **[Package name] version**: [VERSION] ([compatibility note])
- **[Related package] version**: [VERSION] ([usage note])
- **Integration**: [Brief description of integration mechanism]

### With [Related Package/System 2]

**Pattern**: [Brief description of integration pattern]

```[language]
// [Description of integration code]
[code example showing integration]
```

**[Related systems/packages] integrated**:
- [Package/System name] ([services using it]): [Purpose]
- [Package/System name] ([services using it]): [Purpose]

[Repeat for each major integration pattern discovered]

## Performance Characteristics

### Benchmarks from Services

**[service-name]** ([brief context]):
- [Metric 1]: [VALUE] ([conditions/context])
- [Metric 2]: [VALUE]
- [Metric 3]: [VALUE]
- [Metric 4]: [VALUE]

**[service-name]** ([brief context]):
- [Metric 1]: [VALUE] ([conditions/context])
- [Metric 2]: [VALUE]
- [Metric 3]: [VALUE]
- [Metric 4]: [VALUE]

### Bottlenecks Observed

1. **[Bottleneck Name]**: [Description of the issue]. Solution: [How it was addressed or recommendations].

2. **[Bottleneck Name]**: [Description of the issue]. Solution: [How it was addressed or recommendations].

3. **[Bottleneck Name]**: [Description of the issue]. Solution: [How it was addressed or recommendations].

## Configuration Patterns

### Common Configuration Across Services

```[language]
// [Description of configuration pattern]
[code example showing typical configuration]
```

**Settings summary**:
- **[Setting Name]**: [Description and values used] ([rationale])
- **[Setting Name]**: [Description and values used] ([rationale])
- **[Setting Name]**: [Description and values used] ([rationale])
- **[Setting Name]**: [Description and values used] ([rationale])

## Security Considerations

### [Security Aspect 1]

**Used in**: [List of services]

```[language]
// [Description of security configuration]
[code example showing security setup]
```

### [Security Aspect 2]

**Status**: [Description of implementation status]
- [Detail 1]: [Information]
- [Detail 2]: [Information]

### [Security Aspect 3]

**Implemented via [mechanism]** in [service-name]:
- [Security measure 1]
- [Security measure 2]
- [Security measure 3]

## Dependencies and Compatibility

### Direct Dependencies

```[config-format]
# [Description of dependency declaration location]
[package-name] = "[VERSION]"
```

### Related Ecosystem Packages

| Package | Version | Used By | Purpose |
|---------|---------|---------|---------|
| `[package-name]` | [VERSION] | [X] services | [Brief purpose] |
| `[package-name]` | [VERSION] | [X] services | [Brief purpose] |
| `[package-name]` | [VERSION] | [X] services | [Brief purpose] |

### Compatibility Matrix

- **[Language/Runtime version]**: [VERSION_REQUIREMENT] ([actual version used])
- **[Related package 1]**: [VERSION] ([compatibility status])
- **[Related package 2]**: [VERSION] ([compatibility status])
- **[Related package 3]**: [Notes on usage or compatibility]

## Migration Notes

### Recent Upgrade: [OLD_VERSION] to [NEW_VERSION]

**Changes made** (based on git history or migration experience):
1. [Change description and reason]
2. [Change description and reason]
3. [Change description and reason]

**Breaking changes**: [Description or "None affecting this codebase"]

### Future Upgrade Considerations ([CURRENT_VERSION] → [FUTURE_VERSION])

**Anticipated breaking changes** (from roadmap/changelog):
1. [Expected change and impact]
2. [Expected change and impact]
3. [Expected change and impact]

**Estimated effort**: [Low/Medium/High] ([time estimate or rationale])

## Recommendations

### Best Practices Observed

1. ✅ **[Practice Name]**: [Description of what's being done well]
2. ✅ **[Practice Name]**: [Description of what's being done well]
3. ✅ **[Practice Name]**: [Description of what's being done well]
4. ✅ **[Practice Name]**: [Description of what's being done well]

### Suggested Improvements

1. **[Improvement Title]**: [Brief description]
   - Current: [Current state or limitation]
   - Recommended: [Suggested improvement and benefits]

2. **[Improvement Title]**: [Brief description]
   - Current: [Current state or limitation]
   - Recommended: [Suggested improvement and benefits]

3. **[Improvement Title]**: [Brief description]
   - Current: [Current state or limitation]
   - Recommended: [Suggested improvement and benefits]

[Add more recommendations as discovered during analysis]

## Testing Patterns

### [Test Type] with [Package Name]

**Pattern**: [Brief description of testing approach]

```[language]
// [Description of test pattern]
[code example showing test implementation]
```

**Test coverage**:
- [service-name]: [X]% coverage ([Y] test cases)
- [service-name]: [X]% coverage ([Y] test cases)
- [service-name]: [X]% coverage ([Y] test cases)

## Related Documentation

- [[Package Name] Official Docs]([URL])
- [Internal Documentation Title]([relative-path])
- [Related Service Analysis]([relative-path])
- [Architecture Documentation]([relative-path])

## Analysis Summary

**Overall Assessment**: [2-3 sentence summary of how well the package is integrated, its role in the codebase, and general observations about usage quality]

**Key Strengths**:
- [Strength 1]
- [Strength 2]
- [Strength 3]
- [Strength 4]

**Areas for Improvement**:
- [Improvement area 1]
- [Improvement area 2]
- [Improvement area 3]
- [Improvement area 4]
