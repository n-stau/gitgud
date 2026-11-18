---
name: write-readme
description: Write or rewrite a README.md so the repo looks like a well-run open-source project from a large company (Vercel, Astral, Anthropic, Stripe, Microsoft) - centered header with logo, a few flat badges and a one-line tagline, then highlights, install, quick start, docs, contributing and license, compact and scannable, every command verified against the repo - plus the GitHub "About" box (description, website, topics). Use when the user asks for a README or a repo description/About/topics, wants a repo to look professional or ready to publish, or asks to clean up, shorten or restructure existing docs.
---

# Write a README like a big-company open-source repo

What those READMEs share (next.js, vite, uv, playwright, anthropic-sdk-python, openai-agents-python): the README is the front door, not the manual. The reader learns what the project is in one line, sees why it is good in a short list, and can run it within one copy-paste. Everything deeper lives in `docs/` or a docs site and gets a link.

## Workflow

1. **Read the repo first.** Package manifest (name, version, license, scripts, engines), entry points, existing docs, CI workflows, LICENSE, CONTRIBUTING, SECURITY, examples, screenshots. Note the real install and run commands.
2. **Pick the type**, since it decides the middle part:
   - library/SDK: install, minimal usage snippet, requirements
   - CLI/tool: install, 2-4 example commands with what they do
   - app/service: screenshot, quick start (clone, configure, run), configuration table
   - collection/monorepo: install, catalog table (name, one-line purpose), layout
3. **Write it** from the skeleton below. Drop any section that would be empty or padded.
4. **Verify.** Run or at least trace every command and code snippet (scripts exist, paths exist, flags are real). Check every relative link and image path exists. Any badge must point at something real (published package, existing workflow, real license).
5. **Fill the GitHub "About"** (see below) when the repo is on GitHub.
6. **Report** to the user what you could not verify (commands not run, missing LICENSE, placeholder links).

## GitHub "About" (description, website, topics)

The About box is what people see in search results, profile pins and link previews, so it gets the same care as the tagline.

- **Description:** the tagline, shortened to one plain sentence of 60-120 characters (GitHub allows 350). Start with what it is, no "A repo for", no emoji, no trailing period needed. Example: `Fast Python package and project manager, written in Rust`.
- **Website:** only a real URL (docs site, live demo, package page). Leave empty rather than linking the repo itself.
- **Topics:** 4-8 lowercase, hyphenated, real terms people search for: language, framework, domain, type (`python`, `fastapi`, `postgis`, `parking`, `rest-api`). No vanity tags, no duplicates of the name.

Show the current values (`gh repo view --json description,homepageUrl,repositoryTopics`) next to the proposal, then apply only after the user says yes (it writes to GitHub):

```bash
gh repo edit OWNER/REPO --description "..." --homepage "https://..." --add-topic python --add-topic fastapi
gh repo edit OWNER/REPO --remove-topic old-topic     # drop outdated topics
```

For several repos at once, show one table (repo, current, proposed description, topics) and take one go for the whole list; skip forks and repos the user excludes.

## Skeleton

```markdown
<div align="center">

<img src="assets/logo.svg" alt="Project logo" height="96" />   <!-- only if a logo exists -->

# Project Name

Project Name is a <category> for <who> that <does what, concretely>.

[![CI](...)](...) [![npm](...)](...) [![License](...)](LICENSE)

[Documentation](...) · [Examples](...) · [Changelog](...)

</div>

<!-- optional: one hero screenshot/GIF/diagram, with alt text and a one-line caption -->

## Highlights

- **Fast**: concrete fact or number, link for proof.
- 4-7 bullets, each a capability with a specific detail, not an adjective.

## Installation

    one command, copy-pasteable

## Quick start

    smallest complete example that actually runs, with its output if short

## Documentation

One sentence plus link. Or a short table of the main docs pages.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). (One line. Mention the dev command if there is no CONTRIBUTING.)

## License

[MIT](LICENSE) © Owner
```

Optional sections, only when they carry weight: **Requirements** (runtimes/versions), **Configuration** (table: variable, default, description), **Project layout** (short tree with one comment per line), **Security** (link SECURITY.md or "report privately to ..."), **Acknowledgements**, **FAQ** (max 3 entries).

## Style rules

- **Length:** library/tool 40-150 lines. If it gets longer, move detail to `docs/` and link it. No table of contents under ~150 lines.
- **Tagline:** one sentence, noun first: "X is a ... that ...". No "Welcome to", no "This repository contains".
- **Headings:** sentence case, short nouns ("Installation", "Quick start"). No emoji in headings; one brand emoji in the title is the most allowed.
- **Badges:** 2-4 flat badges max, same style and color family, real data only (version, CI, license, chat). No walls of "made with" badges.
- **Voice:** direct, present tense, second person in instructions ("Run", "Set"). Active verbs. Facts over adjectives: "10-100x faster than pip" beats "blazingly fast".
- **Code blocks:** always fenced with a language tag (`bash`, `python`, `ts`). Commands without `$` prompts, no output mixed in. One command per line, copy-paste safe.
- **Lists vs. tables:** bullets for highlights, tables for catalogs and config (3 columns max). Keep table cells to one line.
- **Images:** light/dark variants via `<picture>` when the logo needs them; always `alt`; height-limited (logo 60-128 px); relative paths into an `assets/` or `.github/` folder.
- **Links:** relative for repo files, absolute for external. Link text says where it goes ("Documentation", not "here").
- **Honesty:** no features that do not exist yet, no fake stars/downloads, no placeholder badges. Mark planned work as "Roadmap" or leave it out.
- **Language:** match the repo and audience; default English for public repos.

## Don'ts

- No marketing wall above the fold, no five-paragraph intro.
- No full API reference, changelog or setup troubleshooting inside the README.
- No duplicated info (install in two places, license text pasted inline).
- No HTML beyond the centered header and `<picture>`; GitHub strips styles anyway.
- Do not invent a logo, docs URL, package name or license. Ask or leave the element out.
