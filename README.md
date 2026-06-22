# SPQ - Share Project

QGIS plugin to **version and share the QGIS project itself** (not the layer data)
when stored in **PostgreSQL** or in a **GeoPackage**.

> SPQ = *Share Project for QGIS*. By Vertical Srl.

When a project is saved in QGIS' native PostgreSQL or GeoPackage project storage
(the `qgis_projects` table), several people can work on it. This plugin adds a
**version history** and an **out-of-sync notification** on top of it, so one
user's changes are not silently lost.

> Single codebase compatible with **QGIS 3 (Qt5)** and **QGIS 4 (Qt6)**.

## Requirements

- QGIS ≥ 3.22 (also runs on QGIS 4 / Qt6)
- A QGIS project stored in **PostgreSQL** (`postgresql` storage) or in a
  **GeoPackage** (`geopackage` storage)
- For PostgreSQL: the `psycopg2` Python module in the QGIS Python environment
  (GeoPackage uses the bundled `sqlite3`, no extra dependency)

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

The toolbar exposes:

| Command | What it does |
|---------|--------------|
| Save the project | Saves the project like the normal QGIS command; while versioning is on it also offers a snapshot |
| Versioning on | Toggles versioning: while on, every save records a version and the plugin periodically checks the storage |
| Version history | Opens the project version history |
| Reload the latest version | Reloads the current version from the storage |
| Check for updates | Immediately checks for a newer version in the storage |
| Save a local copy as QGZ | Exports the current project to a `.qgz` file |
| 🔔 Notification bell | Idle when up to date; red dot when a newer version exists. Click it to see details and choose whether to reload |
| ℹ️ About | Shows version and usage instructions |

In the **history window** each version can be *promoted* to the working copy
for everyone, *downloaded* as a `.qgz`, or *deleted*.

Commands are enabled only when the open project is stored in PostgreSQL or in a
GeoPackage.

## How versioning works

Versioning is a binary choice of the toggle: **while it is on, every save records
a version** in the `qgis_projects_share_history` table (project name, content,
metadata, author, time, optional notes, checksum). The save dialog only collects
optional notes — *Save with notes* or *Skip*; the version is recorded either way.

The plugin talks to the storage through a small backend abstraction with two
implementations: PostgreSQL (`psycopg2`) and GeoPackage (`sqlite3`). For
GeoPackage, the checksum and the snapshot id are computed in Python (SQLite has
no `md5()`/`uuid`), and the author falls back to the OS user since GeoPackage
does not record a per-save user like PostgreSQL.

## Known limitations

- Concurrency is *notified*, not *prevented* (no optimistic check on write yet).
- The out-of-sync comparison still considers the timestamp/author in addition to
  the content checksum.
- `promote` overwrites the working copy without archiving it first.
- For GeoPackage, sharing means a shared file: SQLite file locking and the
  way SQLite touches the file apply.

## Report a problem

- Issues: https://github.com/Verticalsrl/qgs-share/issues
- Email: supporto@vertical-srl.it
- Web: https://vertical-srl.it

## License

Vertical Srl — https://vertical-srl.it
