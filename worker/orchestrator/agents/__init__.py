"""Agent bodies (A1–A9).

Each agent is a plain module of pure-ish functions that the orchestrator node
in `orchestrator.nodes` calls. Agents never touch the LangGraph state machine,
the checkpointer, or the gates directly — the node is the seam. Their only
external dependency is the LLM gateway (`app.gateway.llm_call`) and the ORM.
"""
