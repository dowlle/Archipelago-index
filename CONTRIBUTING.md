# Contributing

This repository is a fork of [Eijebong/Archipelago-index](https://github.com/Eijebong/Archipelago-index), tracking [mooinglemur/Archipelago-index](https://github.com/mooinglemur/Archipelago-index) as the community-curated upstream.

## Where to request new APWorlds

**Open community contributions go to the upstream:** [mooinglemur/Archipelago-index](https://github.com/mooinglemur/Archipelago-index). That repository is the canonical place to:

- Add a new APWorld to the index
- Update an existing APWorld's version
- Report issues with an indexed APWorld

This fork (`dowlle/Archipelago-index`) is primarily a downstream sync target plus a testbed for index tooling (see `SECURITY.md`). PRs opened directly here are welcome but the same change will need to land upstream to reach the wider ecosystem.

## How to add or update a world

The mechanics are unchanged from upstream. See [`README.md`](./README.md) for the full schema:

1. Add or edit `index/{apworld}.toml` matching the apworld name.
2. Set `name` (must match the in-YAML world name), optional `display_name`, optional `home`, optional `tags`.
3. Add a `[versions]` section with one entry per release. Versions must be valid [semver](https://semver.org/).
4. Source can be `url` (preferred, points at a release artifact) or `local` (file checked into `apworlds/`). For semver-tagged release URLs, use a `default_url` template at the top level.

## Inclusion criteria

See `README.md` -- the upstream criteria apply unchanged: no banned content, no large opaque binary blobs, no remote resources during generation, no ROM dependency for new worlds, fuzzer failure rate below 1%, beta versions of core games must use a distinct world name.

## Security audit

PRs opened against this fork run through an automated source-level security audit before merge. See `SECURITY.md` for what it checks, what verdicts mean, and how to respond to a `NEEDS_REVIEW` or `FAIL` result.
