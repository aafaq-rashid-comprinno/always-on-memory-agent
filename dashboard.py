"""
Always-On Memory Agent - Streamlit Dashboard

Standalone UI that connects to the agent's HTTP API.

Usage:
    streamlit run dashboard.py
"""

import json
import os
import time

import requests
import streamlit as st

# ─── Config ────────────────────────────────────────────────────

AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8888")

# ─── Page Config ───────────────────────────────────────────────

st.set_page_config(
    page_title="Memory Agent",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── API Helpers ───────────────────────────────────────────────


def api_get(endpoint: str, params: dict = None) -> dict | None:
    try:
        r = requests.get(f"{AGENT_URL}{endpoint}", params=params, timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error(f"Cannot connect to agent at {AGENT_URL}. Is it running?")
        return None
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_post(endpoint: str, data: dict = None) -> dict | None:
    try:
        r = requests.post(f"{AGENT_URL}{endpoint}", json=data, timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error(f"Cannot connect to agent at {AGENT_URL}. Is it running?")
        return None
    except Exception as e:
        st.error(f"API error: {e}")
        return None


# ─── Sidebar ───────────────────────────────────────────────────

with st.sidebar:
    st.title("🧠 Memory Agent")
    st.caption("AWS Bedrock Edition")
    st.divider()

    # Connection status
    health = api_get("/health")
    if health:
        st.success("Connected")
        st.caption(f"Model: `{health.get('model', 'unknown')}`")
        st.caption(f"Region: `{health.get('region', 'unknown')}`")
    else:
        st.error("Disconnected")
        st.caption(f"Trying: {AGENT_URL}")
        st.stop()

    st.divider()

    # Stats
    stats = api_get("/status")
    if stats:
        col1, col2, col3 = st.columns(3)
        col1.metric("Memories", stats.get("total_memories", 0))
        col2.metric("Pending", stats.get("unconsolidated", 0))
        col3.metric("Insights", stats.get("consolidations", 0))

    st.divider()

    # Actions
    if st.button("🔄 Consolidate Now", use_container_width=True):
        with st.spinner("Consolidating..."):
            result = api_post("/consolidate")
            if result:
                st.success("Done!")
                st.caption(result.get("response", "")[:200])
                time.sleep(1)
                st.rerun()

    st.divider()

    with st.expander("⚠️ Danger Zone"):
        if st.button("🗑️ Clear All Memories", type="primary"):
            result = api_post("/clear")
            if result:
                st.success(f"Cleared {result.get('memories_deleted', 0)} memories")
                time.sleep(1)
                st.rerun()

# ─── Main Tabs ─────────────────────────────────────────────────

tab_query, tab_ingest, tab_memories, tab_insights = st.tabs(["💬 Query", "📥 Ingest", "📚 Memories", "💡 Insights"])

# ─── Query Tab ─────────────────────────────────────────────────

with tab_query:
    st.header("Ask Your Memory")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("What do you want to know?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = api_get("/query", params={"q": prompt})
                if result:
                    answer = result.get("answer", "No response")
                    st.markdown(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})

# ─── Ingest Tab ────────────────────────────────────────────────

with tab_ingest:
    st.header("Feed Information")

    col_text, col_file = st.columns(2)

    with col_text:
        st.subheader("📝 Text")
        text_input = st.text_area("Enter information:", height=200, placeholder="Paste notes, articles, ideas...")
        source_input = st.text_input("Source (optional)", placeholder="e.g., meeting, article")

        if st.button("💾 Store", disabled=not text_input.strip()):
            with st.spinner("Processing..."):
                result = api_post("/ingest", {"text": text_input, "source": source_input or "dashboard"})
                if result:
                    st.success("Stored!")
                    st.caption(result.get("response", "")[:300])

    with col_file:
        st.subheader("📎 File Upload")
        st.caption("Text files via upload. Images/PDFs via `./inbox/` folder.")

        uploaded = st.file_uploader("Choose a file", type=["txt", "md", "json", "csv", "log", "yaml", "yml"])
        if uploaded:
            # Read immediately on upload (before any rerun clears it)
            file_content = uploaded.read().decode("utf-8", errors="replace")[:10000]
            file_name = uploaded.name

            if file_content.strip():
                st.caption(f"📄 {file_name} ({len(file_content)} chars)")
                if st.button("📤 Ingest File"):
                    with st.spinner("Processing..."):
                        result = api_post("/ingest", {"text": file_content, "source": file_name})
                        if result:
                            st.success(f"Ingested: {file_name}")
                            st.caption(result.get("response", "")[:300])
            else:
                st.warning("File is empty.")

# ─── Memories Tab ──────────────────────────────────────────────

with tab_memories:
    st.header("Memory Store")

    if st.button("🔄 Refresh"):
        st.rerun()

    data = api_get("/memories")
    if not data or not data.get("memories"):
        st.info("No memories yet. Ingest some information first!")
    else:
        memories = data["memories"]
        st.caption(f"{len(memories)} memories")

        for mem in memories:
            importance = mem.get("importance", 0)
            icon = "🟢" if importance >= 0.7 else "🟡" if importance >= 0.4 else "⚪"
            status = "✅" if mem.get("consolidated") else "⏳"

            with st.expander(f"{icon} #{mem['id']} {status} — {mem['summary'][:80]}"):
                st.markdown(f"**{mem['summary']}**")

                cols = st.columns([2, 2, 1])
                with cols[0]:
                    entities = mem.get("entities", [])
                    if entities:
                        st.caption(f"🏷️ {', '.join(entities)}")
                with cols[1]:
                    topics = mem.get("topics", [])
                    if topics:
                        st.caption(f"📂 {', '.join(topics)}")
                with cols[2]:
                    if st.button("🗑️", key=f"del_{mem['id']}"):
                        api_post("/delete", {"memory_id": mem["id"]})
                        st.rerun()

                st.caption(
                    f"Source: {mem.get('source', '-')} | "
                    f"Importance: {importance:.1f} | "
                    f"Created: {mem.get('created_at', '')[:16]}"
                )

# ─── Insights Tab ──────────────────────────────────────────────

with tab_insights:
    st.header("💡 Consolidation Insights")
    st.caption("Patterns and connections discovered across your memories (like the brain during sleep).")

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Refresh Insights"):
            st.rerun()

    data = api_get("/consolidations")
    if not data or not data.get("consolidations"):
        st.info(
            "No insights yet. Ingest 2+ memories and click **Consolidate Now** in the sidebar "
            "to discover patterns."
        )
    else:
        consolidations = data["consolidations"]
        st.caption(f"{len(consolidations)} consolidation(s)")

        for i, cons in enumerate(consolidations, 1):
            with st.expander(f"💡 Insight #{i}: {cons['insight'][:80]}", expanded=(i == 1)):
                st.markdown(f"### Insight")
                st.info(cons["insight"])

                st.markdown(f"### Summary")
                st.write(cons["summary"])

                source_ids = cons.get("source_ids", [])
                if source_ids:
                    st.caption(f"🔗 Based on memories: {', '.join(f'#{mid}' for mid in source_ids)}")

# ─── Footer ───────────────────────────────────────────────────

st.divider()
st.caption(f"Always-On Memory Agent | Connected to `{AGENT_URL}`")
