# Creative AI Tools

AI tools for visual creative media (images and video): tools that generate
media, and tools that analyse it. Each folder is a standalone tool with its own
README, dependencies and virtual environment. 

| Tool | What it does | Shape |
| --- | --- | --- |
| [`world-builder/`](world-builder/README.md) | Build worlds with one visual style: characters, locations, objects, and episodes storyboarded scene by scene | FastAPI backend + Streamlit UI |
| [`youtube-scout/`](youtube-scout/README.md) | Small read-only YouTube Data API tools: channels, uploads, search, creators, comments, featured channels and subscriptions, printed as JSON | One-file Python CLI (`yt`) plus a Claude plugin with four YouTube research skills |
| [`video-production/`](video-production/README.md) | Edit footage into a long-form (16:9) and a short-form (9:16) video, each with a Shotcut project | Claude plugin with one skill (`edit-video`) |

Start with the README of the tool you want to use; each one explains its own
setup. World Builder keeps its worlds in `data/assets/` at the repository root
(gitignored). API keys live in each tool's `.env` (see its `.env.example`) and are
never committed.

## Claude plugins

The repository is a Claude plugin marketplace (`.claude-plugin/marketplace.json`).
Tools that ship skills are listed there: `youtube-scout` and `video-production`. Add
the marketplace with `claude plugin marketplace add MarianoOG/Creative-AI-Tools`,
then `claude plugin install <plugin>@creative-ai-tools`.
