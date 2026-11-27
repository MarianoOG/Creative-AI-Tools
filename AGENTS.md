# What belongs in this repository

This repository is public. It holds AI tools for visual creative media (images and video): tools that generate media and tools that analyse it, and the Claude plugins that drive them.

## Admission

- **Visual media only.** A tool or skill is about making, editing or analysing images or video, or about the platforms that carry them. Anything else belongs elsewhere.
- **Nothing private.** No personal names, accounts, channel or project IDs, file paths from a personal machine, brand or business strategy, or employer information. A reader who has never heard of the author must be able to use every file as it is.
- **Method, not identity.** Keep how something is done (specs, steps, rules of thumb). Leave out what one person decided about their own work. When a skill needs the user's own context, it asks for it or reads what the user's instructions name, as `youtube-scout` does.

## Plugins

- **Self-contained.** A plugin's skills reference only skills, files and tools inside the same plugin. Never name a skill from another plugin or from outside this repository.
- Each plugin has its own folder, `.claude-plugin/plugin.json`, a README, and an entry in `.claude-plugin/marketplace.json`.
- No `version` field in `plugin.json`: updates track commits.

## Writing

Documents here follow the same rules as any document an agent reads: one purpose per document, one place per fact, facts in references and steps in skills, no attribution and no temporary state.
