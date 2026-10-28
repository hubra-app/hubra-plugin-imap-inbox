# Shared inbox (IMAP)

A plugin for [Hubra](https://hubra.club). Read club mailboxes hosted anywhere (Infomaniak, Hostpoint, Gmail with an app password...) inside Hubra. Read-only by default, each mailbox visible to one group, passwords stored encrypted.

**Version** 1.0.0 · **Works with** Hubra >=0.1,<1 · **Plugin id** `imap-inbox`

## Install

Platform admins install it from the plugin catalogue in the manager portal
(official Marketplace, <https://plugins.hubra.club/index.json>, signed with
the Hubra project key). Clubs then switch it on under Einstellungen → Module
& Plugins.

## Develop

Clone this repository into `plugins/imap-inbox` of a Hubra checkout. Its tests
then run with Hubra's (`cd app/backend && pytest ../../plugins/imap-inbox`), and
`npm run build:plugin` in `app/frontend` builds its frontend. The workflow
does the same against Hubra's `main` on every push and pull request.

## Releasing

Bump `version` in `plugin.yaml`, add a `## <version>` section to
`CHANGELOG.md`, commit, then publish a GitHub release tagged `v<version>`
(web UI, or `gh release create v<version> --target main --notes ""`). The
workflow tests the plugin and builds its frontend; a separate job in the
`plugin-signing` environment, the only one with the `HUBRA_SIGNING_KEY`
secret, signs it; then `imap-inbox-<version>.zip` is attached to the release. Files listed in `.releaseignore` stay out of the zip.

Source: <https://github.com/hubra-app/hubra-plugin-imap-inbox>
