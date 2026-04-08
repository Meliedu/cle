Start the frontend and backend dev servers side-by-side in tmux.

Use the current tmux session (do NOT create a new session). Create a single new window named "dev" with two vertical panes:
- Left pane: backend server (`cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`)
- Right pane: frontend server (`cd frontend && npm run dev`)

Steps:
1. Detect the current tmux session name using `tmux display-message -p '#S'`
2. Create a new window in that session: `tmux new-window -t <session> -n dev`
3. Send the backend start command to the left pane
4. Split the window horizontally (left/right): `tmux split-window -h -t <session>:dev`
5. Send the frontend start command to the right pane
6. Balance the panes: `tmux select-layout -t <session>:dev even-horizontal`

Do NOT switch the user's terminal to the new window — just create it in the background. Report the window name when done.
