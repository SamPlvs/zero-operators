# Zero Operators Documentation

This directory contains the source for [docs.zero-operators.dev](https://docs.zero-operators.dev) — the public Zero Operators documentation site, built with [Mintlify](https://mintlify.com/).

## Local development

```bash
# Install the Mintlify CLI (one-time)
npm install -g mintlify

# From this directory:
cd docs
mintlify dev
```

The dev server runs on [http://localhost:3000](http://localhost:3000) and live-reloads on `.mdx` saves.

## Content structure

```
docs/
├── mint.json                 # site config: nav, colours, logo
├── favicon.svg
├── logo/
│   ├── light.svg             # logo on paper backgrounds
│   └── dark.svg              # logo on canvas backgrounds
├── introduction.mdx          # landing page
├── quickstart.mdx
├── installation.mdx
├── concepts/
│   ├── overview.mdx
│   ├── the-plan.mdx
│   ├── the-oracle.mdx
│   ├── the-team.mdx
│   ├── phases-and-gates.mdx
│   ├── memory-and-continuity.mdx
│   └── low-token-mode.mdx       # the cost-saving preset
├── cli/
│   ├── overview.mdx
│   ├── init.mdx
│   ├── draft.mdx
│   └── build.mdx
└── reference/
    ├── low-token-preset.mdx     # one-page low-token preset card
    └── cost-benchmark.mdx       # MNIST cost comparison methodology + results
```

Pages not referenced in `mint.json`'s `navigation` won't appear on the site.

## Adding a new page

1. Create the `.mdx` file under the appropriate section dir.
2. Add the path (without `.mdx`) to the relevant `pages` array in `mint.json`.
3. Frontmatter requires `title` and `description`.
4. Use Mintlify components: `<Card>`, `<CardGroup>`, `<Steps>`, `<Step>`, `<Tabs>`, `<Tab>`, `<Note>`, `<Tip>`, `<Warning>`, `<AccordionGroup>`, `<Accordion>`. Reference: [Mintlify components](https://mintlify.com/docs/content/components).

## Brand reference

The docs site uses ZO's brand v2 system from `design/`:

| Token | Value | Usage |
|-------|-------|-------|
| `primary` | `#D87A57` (coral) | links, CTAs, accents |
| `light bg` | `#F4EFE6` (paper) | light mode background |
| `dark bg` | `#12110F` (canvas) | dark mode background |
| `ink` | `#1A1712` | light-mode text |
| `cream` | `#EBE3D2` | dark-mode text |
| Sans | Geist | body + headings |
| Mono | JetBrains Mono | code blocks |

See `design/styles.css` and `design/brand-system.html` for the canonical reference.

## Deploying

The site auto-deploys on push to `main` once a Mintlify project is connected to the repo:

1. Sign up at [mintlify.com](https://mintlify.com/) (free for OSS).
2. Connect the `SamPlvs/zero-operators` GitHub repo.
3. Point the project at the `docs/` directory (Mintlify reads `mint.json` from there).
4. Add the `docs.zero-operators.dev` custom domain in the Mintlify dashboard.
5. Update DNS — point a CNAME to Mintlify per their dashboard instructions.

After setup, every push to `main` that touches `docs/` re-deploys the site.

## Content sources we're migrating from

This site's content is being migrated from existing repo locations:

| Source | Destination |
|--------|-------------|
| `README.md` (parts) | `docs/quickstart.mdx`, `docs/introduction.mdx` |
| `docs/COMMANDS.md` | `docs/cli/*.mdx` (in progress) |
| `docs/SAMPLE_PROJECT.md` | `docs/tutorials/*.mdx` (planned) |
| `docs/TROUBLESHOOTING.md` | `docs/resources/troubleshooting.mdx` (planned) |
| `docs/DELIVERY_STRUCTURE.md` | `docs/architecture/delivery-structure.mdx` (planned) |
| `specs/*.md` | `docs/concepts/*.mdx` (in progress) |
| `.claude/agents/*.md` | `docs/reference/agents.mdx` (planned) |
| `memory/zo-platform/PRIORS.md` | `docs/resources/priors.mdx` (planned) |
| `memory/zo-platform/DECISION_LOG.md` | `docs/resources/changelog.mdx` (planned) |

Existing `.md` files stay in place during the transition; the README still links to them. They'll be retired once the Mintlify site is live and content has been migrated.

## Contributing

Spot a typo or wrong example? Every page on the live site has an "Edit on GitHub" link in the footer. One click takes you to the source file. PRs welcome.
