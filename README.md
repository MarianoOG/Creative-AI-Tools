# Creative AI Tools

AI tools for visual creative media (images and video): tools that generate
media, and tools that analyse it. Each folder is a standalone tool with its own
README, dependencies and virtual environment. 

| Tool | What it does | Shape |
| --- | --- | --- |
| [`world-builder/`](world-builder/README.md) | Build worlds with one visual style: characters, locations, objects, and episodes storyboarded scene by scene | FastAPI backend + Streamlit UI |
| [`youtube-scout/`](youtube-scout/README.md) | Small read-only YouTube Data API tools: channels, uploads, search, creators, comments, featured channels and subscriptions, printed as JSON | One-file Python CLI (`yt`), built to be driven by a script, an agent or a Claude session |

Start with the README of the tool you want to use; each one explains its own
setup. World Builder keeps its worlds in `data/assets/` at the repository root
(gitignored). API keys live in each tool's `.env` (see its `.env.example`) and are
never committed.
