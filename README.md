# Vertical Project Share

QGIS plugin to **version and share** QGIS projects stored in **PostgreSQL**.

When a project is saved in QGIS' native PostgreSQL project storage (the
`qgis_projects` table), several people can work on it. This plugin adds a
**version history** and a **out-of-sync notification** on top of it, so one
user's changes are not silently lost.

> ⚠️ Status: `experimental`. Single codebase compatible with **QGIS 3 (Qt5)**
> and **QGIS 4 (Qt6)**.

## Requirements

- QGIS ≥ 3.22 (also runs on QGIS 4 / Qt6)
- A QGIS project stored in **PostgreSQL** (`postgresql` storage)
- The `psycopg2` Python module available in the QGIS Python environment

## Installation

The plugin itself is the `vertical_projectshare/` folder. Copy it into the QGIS
plugins directory:

| OS | Path |
|----|------|
| Linux | `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/` |
| Windows | `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\` |
| macOS | `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/` |

Then restart QGIS (or *Plugins → Reload plugin*) and enable it from
*Plugins → Manage and Install Plugins*.

## Usage

The **VerticalShare** toolbar exposes:

| Command | What it does |
|---------|--------------|
| Save the project | Saves the project like the normal QGIS command; while versioning is on it also offers a snapshot |
| Versioning on | Toggles versioning: while on, every save records a version and the plugin periodically checks the database |
| Version history | Opens the project version history |
| Reload the latest version from the database | Reloads the current version from the database |
| Check the database for updates | Immediately checks for a newer version on the database |
| Save a local copy as QGZ | Exports the current project to a `.qgz` file |
| 🔔 Notification bell | Idle when up to date; red dot when a newer version exists on the database. Click to reload |
| ℹ️ About | Shows version and usage instructions |

In the **history window** each version can be *promoted* to the working copy
for everyone, *downloaded* as a `.qgz`, or *deleted*.

Commands are enabled only when the open project is stored in PostgreSQL.

## How versioning works

Versioning is a binary choice of the toggle: **while it is on, every save records
a version** in the `qgis_projects_share_history` table (project name, content as
`BYTEA`, metadata, author, time, optional notes, md5 checksum). The save dialog
only collects optional notes — *Save with notes* or *Skip*; the version is
recorded either way.

## Known limitations

Tracked in the repository issues:

- Concurrency is *notified*, not *prevented* (no optimistic check on write yet).
- State comparison is sensitive to the timestamp/author in addition to content.
- `promote` overwrites the working copy without archiving it first.

## Report a problem

- Issues: https://github.com/Verticalsrl/qgs-share/issues
- Email: supporto@vertical-srl.it
- Web: https://vertical-srl.it

## License

Vertical Srl — https://vertical-srl.it
