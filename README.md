# Creative AI Tools

AI tools for visual creative media (images and video): tools that generate
media, and tools that analyse it. Each folder is a standalone tool with its own
README, dependencies and virtual environment.

| Tool | What it does | Shape |
| --- | --- | --- |
| [`world-builder/`](world-builder/README.md) | Generate visual assets (characters, objects, locations, scenes) and organise them into worlds | FastAPI backend + Streamlit UI |
| [`youtube-scout/`](youtube-scout/README.md) | Research YouTube channels and videos: search, filter, and score creators and their uploads | Python library, built to be driven by an AI agent |

Start with the README of the tool you want to use; each one explains its own
setup. World Builder keeps its worlds in `data/` at the repository root
(gitignored). API keys live in each tool's `.env` (see its `.env.example`) and are
never committed.
