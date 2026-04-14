Start the full local dev stack (Postgres + backend + frontend).

Prerequisites (run BEFORE opening the tmux window):
1. Bring up Postgres (pgvector) via Docker: `docker compose up -d` from repo root. This starts the `cle-db-1` container on localhost:5432. Required — the backend worker loop will spam `ConnectionRefusedError: [Errno 111]` without it. If `docker` says "not found in this WSL 2 distro", the Windows Docker Desktop binary at `/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe` usually still works — or enable WSL integration in Docker Desktop.

Then use the current tmux session (do NOT create a new session). Create a single new window named "dev" with two vertical panes:
- Left pane: backend server (`cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`)
- Right pane: frontend server (`cd frontend && npm run dev`)

Note: The backend uses a venv at `backend/.venv`. `uvicorn` is NOT on the global PATH — activating the venv first is required.

Steps:
1. Run `docker compose up -d` from repo root to ensure Postgres is up.
2. Detect the current tmux session name using `tmux display-message -p '#S'`.
3. Create a new window in that session: `tmux new-window -t <session> -n dev` (if index 0 collides, pass an explicit free index like `-t <session>:3`).
4. Send the backend start command to the left pane.
5. Split the window horizontally (left/right): `tmux split-window -h -t <session>:dev`.
6. Send the frontend start command to the right pane.
7. Balance the panes: `tmux select-layout -t <session>:dev even-horizontal`.

Do NOT switch the user's terminal to the new window — just create it in the background. Report the window name when done.
