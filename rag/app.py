"""
Service Knowledge RAG — interactive query interface.

Run with:
    streamlit run rag/app.py
"""

import json
import re

import anthropic
import streamlit as st
import streamlit.components.v1 as components

from tools import ARTIFACTS_DIR, TOOL_DEFINITIONS, execute_tool

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Service Knowledge Query", layout="wide")
st.title("Service Knowledge Query")
st.caption("Ask questions about analyzed service architectures")

# ---------------------------------------------------------------------------
# Mermaid rendering
# ---------------------------------------------------------------------------

MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)


def render_mermaid(mermaid_code: str, height: int = 0) -> None:
    """Render a Mermaid diagram via mermaid.js loaded from CDN."""
    lines = mermaid_code.strip().count("\n") + 1
    if height <= 0:
        height = max(300, min(800, lines * 30))
    html = f"""
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <div class="mermaid">
{mermaid_code}
    </div>
    <script>mermaid.initialize({{startOnLoad: true}});</script>
    """
    components.html(html, height=height)


def render_text_with_mermaid(text: str) -> None:
    """Render text that may contain ```mermaid blocks, splitting into
    markdown segments and rendered Mermaid diagrams."""
    parts = MERMAID_BLOCK_RE.split(text)
    # split produces: [before, capture1, between, capture2, after, ...]
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2 == 0:
            # Regular markdown text
            if part.strip():
                st.markdown(part)
        else:
            # Mermaid code captured by the regex
            render_mermaid(part)


def build_system_prompt(services: list[str]) -> str:
    svc_list = ", ".join(services)
    return f"""\
You are a knowledge assistant for software service architectures. You have \
access to detailed analysis artifacts for the following services: {svc_list}.

When answering questions:
1. Identify which service(s) are relevant.
2. Use tools to look up specifics — do not guess from memory. Start with \
list_services or list_components to orient yourself.
3. For component interaction questions, check dependency graphs.
4. For implementation details, read the specific service analysis.
5. For high-level architecture, read the architecture docs.
6. Synthesize from multiple sources when needed.
7. Cite the artifacts / components you reference.

Be precise and technical. If the artifacts lack the information, say so.

## Knowledge Graph Reasoning

You have a `sketch_knowledge_graph` tool that lets you construct Mermaid diagrams \
as an intermediate reasoning step. Call it when:
- Analyzing dependencies across multiple components or services
- Answering relationship questions ("how does X relate to Y")
- Comparing architectural patterns across services
- Tracing data flows through multiple systems
- Synthesizing information from 3+ tool lookups
- The user explicitly asks for a diagram or visualization

Diagram type guidance:
- `graph TD` or `graph LR` for dependency maps and component relationships
- `sequenceDiagram` for interaction flows and data exchange between components

After the diagram is echoed back, examine the relationships you drew, verify \
they are accurate based on the artifacts, and use the diagram to inform your \
final answer. The diagram is rendered live for the user.\
"""

MAX_AGENT_TURNS = 15

# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------


@st.cache_resource
def get_client():
    return anthropic.Anthropic()


client = get_client()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "api_messages" not in st.session_state:
    st.session_state.api_messages = []  # full history for the API
if "turns" not in st.session_state:
    st.session_state.turns = []  # display-friendly turns

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def discover_services():
    """Scan the artifacts directory for available services."""
    return sorted(
        d.name
        for d in ARTIFACTS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


with st.sidebar:
    st.header("Available Services")
    services = discover_services()
    for svc in services:
        st.markdown(f"- **{svc}**")
    st.divider()
    st.markdown("**Example queries**")
    st.markdown(
        """
- How does EigenDA's disperser communicate with nodes?
- What are the main components of AgentKit?
- Explain Symphony's orchestration architecture
- What external dependencies does EigenDA use?
- Compare the architecture patterns across services
"""
    )
    st.divider()
    if st.button("Clear conversation"):
        st.session_state.api_messages = []
        st.session_state.turns = []
        st.rerun()

# ---------------------------------------------------------------------------
# Render previous turns
# ---------------------------------------------------------------------------

for turn in st.session_state.turns:
    with st.chat_message(turn["role"]):
        if turn["role"] == "assistant":
            render_text_with_mermaid(turn["content"])
        else:
            st.markdown(turn["content"])
        if turn.get("tool_calls"):
            with st.expander(f"{len(turn['tool_calls'])} lookups performed"):
                for tc in turn["tool_calls"]:
                    st.code(
                        f"{tc['name']}({json.dumps(tc['input'])})",
                        language="json",
                    )
        if turn.get("diagrams"):
            with st.expander(f"{len(turn['diagrams'])} diagrams generated"):
                for diag in turn["diagrams"]:
                    if diag.get("title"):
                        st.markdown(f"**{diag['title']}**")
                    render_mermaid(diag["mermaid_code"])

# ---------------------------------------------------------------------------
# Handle new input
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Ask about service architectures..."):
    # ---- user message ----
    st.session_state.turns.append({"role": "user", "content": prompt})
    st.session_state.api_messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # ---- agent loop ----
    with st.chat_message("assistant"):
        status = st.status("Thinking...", expanded=True)
        tool_calls_log: list[dict] = []
        diagrams_log: list[dict] = []

        for _ in range(MAX_AGENT_TURNS):
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                system=build_system_prompt(services),
                tools=TOOL_DEFINITIONS,
                messages=st.session_state.api_messages,
            )

            serialized = [block.model_dump() for block in response.content]

            if response.stop_reason == "tool_use":
                # Store the assistant's tool-use turn
                st.session_state.api_messages.append(
                    {"role": "assistant", "content": serialized}
                )

                # Execute each tool call
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        with status:
                            st.write(
                                f"**{block.name}** `{json.dumps(block.input)}`"
                            )
                        result = execute_tool(block.name, block.input)
                        tool_calls_log.append(
                            {"name": block.name, "input": block.input}
                        )

                        # Render knowledge graph diagrams live
                        if block.name == "sketch_knowledge_graph":
                            mermaid_code = block.input.get("mermaid_code", "")
                            title = block.input.get("title", "")
                            if not result.startswith("Error:"):
                                with status:
                                    if title:
                                        st.markdown(f"**{title}**")
                                    render_mermaid(mermaid_code)
                                diagrams_log.append(
                                    {
                                        "mermaid_code": mermaid_code,
                                        "title": title,
                                    }
                                )

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )

                # Feed results back
                st.session_state.api_messages.append(
                    {"role": "user", "content": tool_results}
                )
            else:
                # ---- final text response ----
                label = (
                    f"{len(tool_calls_log)} lookups performed"
                    if tool_calls_log
                    else "Done"
                )
                status.update(label=label, state="complete", expanded=False)

                final_text = "".join(
                    block.text
                    for block in response.content
                    if hasattr(block, "text")
                )
                render_text_with_mermaid(final_text)

                st.session_state.api_messages.append(
                    {"role": "assistant", "content": serialized}
                )
                st.session_state.turns.append(
                    {
                        "role": "assistant",
                        "content": final_text,
                        "tool_calls": tool_calls_log,
                        "diagrams": diagrams_log,
                    }
                )
                break
        else:
            st.error("Reached maximum iterations without a final answer.")
