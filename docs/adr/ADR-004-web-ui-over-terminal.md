# ADR-004 — Web UI with working-spinner instead of a terminal

- **Status:** Accepted
- **Context:** The legacy system runs in a terminal via `.bat` files; Kevin finds this
  unprofessional and engorroso (R11). He wants a web page showing a Windows-style ring of
  moving dots plus one line of status text, and to never see the terminal.
- **Decision:** Build a local **FastAPI backend + single-page static frontend** (EATP-009).
  A "Run" button triggers the pipeline; the page shows the dots spinner + live status via
  **Server-Sent Events** fed by the orchestrator's event bus; then it renders the results
  dashboard. Launch by a one-click script that starts the server and opens the browser —
  no visible terminal interaction required. Dark/violet/Inter per DESIGN-SYSTEM.md.
- **Consequences:** Clean, professional UX; status is legible; no terminal in Kevin's
  face. The orchestrator must emit progress events (designed into EATP-001/008). Streamlit
  is dropped (it spawns a terminal and is less controllable).
- **Alternatives considered:** Keep Streamlit (rejected: terminal window, less control).
  A native desktop app (rejected: heavier, cross-platform packaging cost for no benefit).
