# UI-only delegation

When assigned UI work, read `UI-HANDOFF.md` first. The delegated agent may edit only `monitor/dashboard.html` and, if present in the parent workspace, synchronize the corresponding source `monitor/dashboard.html`.

UI work must preserve monitoring semantics, counts, states, polling, authentication and the API contract. Do not edit Python, backend logic, DB, alerts, Sheet integration, agents, Docker files, dependencies, configuration or secrets to accomplish a UI task.

Do not run tests, install test dependencies or create test environments on this machine. Do not deploy without explicit user authorization. Report the precise upload file and the restart command.

These UI scope restrictions apply to UI-only assignments; they do not authorize unrelated changes or override a later explicit user assignment.
