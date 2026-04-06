# Code Analysis Agent - Complete Workflow Documentation

<overview>
  <purpose>
    Multi-agent codebase analysis system that performs dependency-aware, parallel analysis
    of libraries and applications, generating comprehensive architecture documentation.
  </purpose>

  <architecture>
    <component name="lead-agent">
      <role>Orchestrates the entire analysis workflow and synthesizes documentation</role>
      <responsibilities>
        - Discovers project structure and components
        - Builds dependency graphs (library and application)
        - Spawns specialized subagents for analysis tasks
        - Coordinates parallel execution with dependency ordering
        - Monitors transcript for application completion markers
        - Incrementally processes analyses as they complete
        - Synthesizes comprehensive architecture documentation
      </responsibilities>
      <tools>Task, Glob, Read, Bash, Write</tools>
      <output>
        - files/architecture_docs/architecture.md (comprehensive)
        - files/architecture_docs/quick_reference.md (1-page summary)
      </output>
    </component>

    <component name="code-library-analyzer">
      <role>Deep analysis of library components</role>
      <responsibilities>
        - Explores code structure with Glob, Grep, Read
        - Identifies key components and API surfaces
        - Traces data flows through the library
        - Documents architecture patterns
        - Receives upstream dependency context when analyzing dependent libraries
      </responsibilities>
      <tools>Glob, Grep, Read, Bash, Write</tools>
      <output>files/service_analyses/{library_name}.md</output>
    </component>

    <component name="application-analyzer">
      <role>Deep analysis of application components</role>
      <responsibilities>
        - Analyzes executable systems with business logic
        - Documents system flows and request/response patterns
        - Identifies application-to-application interactions (HTTP, shared DB, message queues)
        - Maps external dependencies
        - Documents how applications use internal libraries
      </responsibilities>
      <tools>Glob, Grep, Read, Bash, Write</tools>
      <output>files/service_analyses/{application_name}.md</output>
    </component>

  </architecture>

  <coordination_mechanism>
    <transcript>
      <location>logs/latest/transcript.txt</location>
      <purpose>
        Live-updated file that serves as the coordination backbone for parallel subagents.
        Lead agent polls this file to detect completion events incrementally.
      </purpose>
      <markers>
        <marker name="APPLICATION_ANALYSIS_COMPLETE">
          <format>[APPLICATION_ANALYSIS_COMPLETE] {component_name}</format>
          <trigger>Written when a single application analyzer completes</trigger>
          <consumer>lead-agent (incremental processing)</consumer>
        </marker>
        <marker name="ALL_APPLICATION_ANALYSIS_COMPLETE">
          <format>[ALL_APPLICATION_ANALYSIS_COMPLETE]</format>
          <trigger>Written when all application analyzers complete</trigger>
          <consumer>lead-agent (triggers final synthesis)</consumer>
        </marker>
      </markers>
    </transcript>

    <subagent_tracking>
      <mechanism>Hook-based tracking system</mechanism>
      <hooks>
        <hook name="PreToolUse">Captures tool invocations before execution</hook>
        <hook name="PostToolUse">Captures tool results after execution</hook>
        <hook name="SubagentStop">Detects subagent completion</hook>
      </hooks>
      <state>
        - Maps parent_tool_use_id → SubagentSession
        - Tracks active analyzer count for completion detection
        - Logs all tool calls to transcript and JSONL file
      </state>
    </subagent_tracking>
  </coordination_mechanism>

  <execution_strategy>
    <principle name="dependency-aware-parallelism">
      Libraries are analyzed in dependency order (depth-first topological), while libraries
      at the same depth level run in parallel. Applications run fully in parallel since they
      don't depend on each other. Lead agent monitors transcript and processes completions
      incrementally.
    </principle>

    <performance_characteristics>
      - Parallel application analysis for maximum throughput
      - Depth-0 libraries (no dependencies) all analyze in parallel
      - Dependent libraries receive upstream context, avoiding redundant discovery
      - Incremental processing allows lead agent to understand architecture progressively
    </performance_characteristics>
  </execution_strategy>

  <data_flow>
    <stage name="discovery">
      <input>Project root path from user</input>
      <process>
        - Detect project type (monorepo, polyrepo, single project)
        - Discover all packages/services via package.json, go.mod, etc.
        - Classify as library or application
        - Build dependency graphs
      </process>
      <output>
        - files/service_discovery/components.json
        - files/dependency_graphs/library_graph.json
        - files/dependency_graphs/application_graph.json (partial, completed later)
      </output>
    </stage>

    <stage name="library-analysis">
      <input>
        - Library dependency graph
        - Component metadata
      </input>
      <process>
        - Phase 1: Analyze depth=0 libraries in parallel (no context needed)
        - Phase 2: For each depth level, analyze libraries after their dependencies complete in parallel
        - Pass upstream context (architecture, API surface, data flows) to dependent libraries
      </process>
      <output>files/service_analyses/{library_name}.md for each library</output>
    </stage>

    <stage name="application-analysis">
      <input>
        - Application list from components.json
        - Completed library analyses (upstream context)
      </input>
      <process>
        - Spawn all application analyzers in parallel
        - Each receives library context for dependencies
        - Identify application-to-application interactions
        - Write completion markers to transcript
      </process>
      <output>
        - files/service_analyses/{application_name}.md for each application
        - Completed application_graph.json with interaction edges
      </output>
    </stage>

    <stage name="architecture-synthesis">
      <input>
        - Library and application analyses (incrementally via transcript polling by lead agent)
        - Complete dependency graphs
        - Documentation templates from templates/
      </input>
      <process>
        - Lead agent polls transcript for [APPLICATION_ANALYSIS_COMPLETE] markers
        - Incrementally processes each completed application analysis
        - When [ALL_APPLICATION_ANALYSIS_COMPLETE] appears, performs final synthesis
        - Uses templates/architecture_template.md and templates/quick_reference_template.md
        - Fills in template placeholders with data from all analyses and graphs
      </process>
      <output>
        - files/architecture_docs/architecture.md
        - files/architecture_docs/quick_reference.md
      </output>
    </stage>

  </data_flow>

  <workflow_steps>
    <step number="1" name="project-discovery">
      Detect project structure, discover components, build initial dependency graphs
    </step>

    <step number="2" name="library-analysis-phase-1">
      Analyze all depth=0 libraries in parallel (no dependencies)
    </step>

    <step number="3" name="library-analysis-phase-2">
      Analyze dependent libraries in topological order, passing upstream context
    </step>

    <step number="4" name="application-analysis-and-synthesis">
      - Spawn all application analyzers in parallel
      - Lead agent polls transcript for [APPLICATION_ANALYSIS_COMPLETE] markers
      - Lead agent incrementally processes completed analyses
      - When [ALL_APPLICATION_ANALYSIS_COMPLETE] appears, lead agent synthesizes architecture docs
    </step>

  </workflow_steps>
</overview>

<phase name="depth-0-libraries">
  <title>Analyze depth=0 Libraries (No Library Dependencies)</title>

  <instructions>
    <for-each target="library in depth=0">
      <spawn-subagent>
        <subagent_type>code-library-analyzer</subagent_type>
        <description>Analyze {library_name}</description>
        <prompt>
          Include library name, path, type, description, classification=library, NO upstream context
        </prompt>
        <execution_mode>IN PARALLEL</execution_mode>
      </spawn-subagent>
    </for-each>

    <wait_condition>
      ALL depth=0 library analyzers must complete before proceeding to next step
    </wait_condition>
  </instructions>
</phase>

<phase name="dependency-ordered-libraries">
  <title>Step 3.2: Analyze Phase 2 Libraries (Dependency Order)</title>

  <algorithm>
    <iterate variable="depth" start="1">
      <for-each target="library_set in nodes_at(depth)">
        <condition>
          <if test="library_set == 0">
            <action>continue</action>
          </if>
        </condition>

        <for-each target="library in library_set">
          <step name="gather-dependencies">
            <description>Get library's DIRECT dependencies using the library graph</description>

            <for-each target="direct dependency">
              <read_analysis>
                <file>files/service_analyses/{dep_name}.md</file>
                <extract_fields>
                  <field name="architecture">overview</field>
                  <field name="key_components">list of main components</field>
                  <field name="api_surface">exported functions/types</field>
                  <field name="data_flows">how data moves through the library</field>
                </extract_fields>
              </read_analysis>
            </for-each>
          </step>

          <step name="spawn-analyzer">
            <spawn-subagent>
              <subagent_type>code-library-analyzer</subagent_type>
              <description>Analyze {library_name}</description>
              <prompt>
                Include library info + classification=library + upstream context from direct dependencies
              </prompt>
            </spawn-subagent>
          </step>
        </for-each>

        <wait_condition>
          <description>Wait for all library analyses to complete</description>
          <signal>subagent task returns "done" signal to globally shared "transcript"</signal>
        </wait_condition>
      </for-each>
    </iterate>
  </algorithm>

  <important>
    <constraint priority="critical">
      Only spawn analyzer after ALL its direct dependencies have completed AND been processed.
    </constraint>
    <note>
      You can spawn multiple library analyzers in parallel if they have the same dependency depth.
    </note>
  </important>
</phase>

<workflow name="parallel-application-architecture">
  <title>Codeified application &lt;&gt; architecture parallel subagent flow</title>

  <pseudocode language="workflow">
<![CDATA[
// Lead agent spawns all application analyzers
application_analysis_tasks = []
for application in applications:
  analysis_subagent_task = code_analyzer_task(application.context)
  analysis_subagent_task.start()
  application_analysis_tasks.append(analysis_subagent_task)

// Lead agent polls transcript for completions
processed_applications = []
while not_all_complete:
  transcript = read_file("logs/*/transcript.txt")

  // Check for individual completions
  for marker in find_markers(transcript, "[APPLICATION_ANALYSIS_COMPLETE]"):
    app_name = extract_component_name(marker)
    if app_name not in processed_applications:
      analysis = read_file(f"files/service_analyses/{{app_name}}.md")
      process_analysis(analysis)  // Build progressive understanding
      processed_applications.append(app_name)

  // Check for all complete
  if "[ALL_APPLICATION_ANALYSIS_COMPLETE]" in transcript:
    break

// Lead agent performs final synthesis
update_application_graph()
synthesize_architecture_documentation()
]]>
  </pseudocode>

  <completion_requirements>
    <wait target="ALL application analyzers" />
    <synthesize target="architecture documentation" agent="lead-agent" />
  </completion_requirements>
</workflow>
