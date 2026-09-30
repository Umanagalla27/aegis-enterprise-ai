# Multi-Agent Framework Comparison: LangGraph vs. CrewAI vs. AutoGen vs. OpenAI Agents SDK

| Feature | LangGraph | CrewAI | AutoGen | OpenAI Agents SDK |
|---|---|---|---|---|
| **Control Flow** | **Deterministic Graph (StateGraph)** | Role-based autonomous crew | Conversational agent chatter | Procedural Python wrapper |
| **Human-in-the-Loop** | **Native `interrupt()` / Checkpointer** | Manual input prompt | Conversational intervention | Manual loop breaks |
| **State Persistence** | **Postgres / Redis Checkpointers** | In-Memory | In-Memory | Developer responsibility |
| **Protocol Support** | **Native Model Context Protocol (MCP)** | Custom tool wrappers | Function schemas | OpenAI tool schemas |
| **Enterprise SLA** | **Mission-critical compliance ready** | Best for content & research | Academic simulation | Lightweight single-vendor |
