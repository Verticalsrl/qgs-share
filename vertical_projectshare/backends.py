"""
Storage backends for Vertical Project Share.

The plugin used to talk to PostgreSQL only. To support GeoPackage too (a SQLite
file), the storage-specific operations live behind a small abstract interface
(`ProjectBackend`) with two implementations:

- `PostgresBackend`  -> psycopg2, schema-qualified tables, server-side md5()/uuid
- `GeoPackageBackend` -> sqlite3 on the .gpkg file; SQLite has no md5()/uuid, so
  checksums (hashlib) and ids (uuid) are computed in Python

The rest of the plugin (toolbar, bell, dialogs, snapper) is storage-agnostic and
only talks to this interface, picking the right backend with `make_backend()`.
"""
import datetime
import getpass
import hashlib
import json
import os
import sqlite3
import urllib.parse
import uuid
from abc import ABC, abstractmethod
from contextlib import closing
from typing import List, Optional

import psycopg2
from psycopg2 import sql

from .project_connector import ProjectUpdateState, DbProjectConnector
from .constants import TABLE_VERTICAL_SHARE, TABLE_PROJECTS_QGIS


class ProjectBackend(ABC):
	"""storage-agnostic interface the snapper talks to.

	`project` and `username` are used for the dialog labels and the snapshot
	author; the methods are the versioning operations."""

	project: str
	username: str

	@abstractmethod
	def get_project_update_state(self) -> Optional[ProjectUpdateState]: ...
	@abstractmethod
	def has_history_table(self) -> bool: ...
	@abstractmethod
	def ensure_history_table(self): ...
	@abstractmethod
	def save_snapshot(self, changename: str, notes: str): ...
	@abstractmethod
	def get_history(self) -> List[dict]: ...
	@abstractmethod
	def get_change_raw(self, changeid: str) -> dict: ...
	@abstractmethod
	def delete_change(self, changeid: str): ...
	@abstractmethod
	def promote(self, changeid: str): ...
	@abstractmethod
	def get_latest_snapshot_hash(self) -> Optional[str]: ...


def make_backend(uri: str) -> ProjectBackend:
	"""pick the backend from the project storage URI scheme"""
	scheme = urllib.parse.urlparse(uri).scheme.lower()
	if "geopackage" in scheme or scheme in ("gpkg", "ogr"):
		return GeoPackageBackend(uri)
	return PostgresBackend(uri)


# --------------------------------------------------------------------------- #
# PostgreSQL
# --------------------------------------------------------------------------- #

class PostgresBackend(ProjectBackend):

	def __init__(self, uri: str):
		self._dbc = DbProjectConnector(uri)
		self.parsed = self._dbc.parsed_uri
		self.project = self.parsed.project
		self.username = self.parsed.username
		self.schema = self.parsed.schema
		self.pgconn = self._dbc.pgconn

	def _raw_conn(self):
		return psycopg2.connect(self.pgconn.connstr)

	def get_project_update_state(self):
		return self._dbc.get_project_update_state()

	def has_history_table(self):
		cols = self.pgconn.get_table_columns(self.schema, TABLE_VERTICAL_SHARE)
		return len(cols) > 0

	def ensure_history_table(self):
		if self.has_history_table():
			return
		query = sql.SQL("""CREATE TABLE IF NOT EXISTS {schema}.{tablename} (
			changeid			VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
			changename			VARCHAR,
			project				VARCHAR NOT NULL,
			content				BYTEA NOT NULL,
			metadata			JSONB,
			changed_by			VARCHAR,
			changed_at			TIMESTAMP DEFAULT now(),
			notes				VARCHAR,
			checksum			VARCHAR
		)""").format(schema=sql.Identifier(self.schema), tablename=sql.Identifier(TABLE_VERTICAL_SHARE))
		with closing(self._raw_conn()) as conn:
			with conn:
				with conn.cursor() as cur:
					cur.execute(query)

	def save_snapshot(self, changename: str, notes: str):
		self.ensure_history_table()
		query = sql.SQL("""
			INSERT INTO {schema}.{table_vertical} (project, metadata, content, changename, changed_by, changed_at, notes, checksum)
			SELECT
				{table_qgis}.name,
				{table_qgis}.metadata,
				{table_qgis}.content,
				{changename},
				{changedby},
				({table_qgis}.metadata->>'last_modified_time')::TIMESTAMP,
				{notes},
				md5({table_qgis}.content)
			FROM {schema}.{table_qgis}
			WHERE {table_qgis}.name = {projectname}
		""").format(
			schema=sql.Identifier(self.schema), table_vertical=sql.Identifier(TABLE_VERTICAL_SHARE), table_qgis=sql.Identifier(TABLE_PROJECTS_QGIS),
			changename=sql.Literal(changename), notes=sql.Literal(notes), changedby=sql.Literal(self.username),
			projectname=sql.Literal(self.project)
		)
		with closing(self._raw_conn()) as conn:
			with conn:
				with conn.cursor() as cur:
					cur.execute(query)

	def get_history(self):
		query = sql.SQL("""
			SELECT changeid, changename, project, metadata, changed_by, changed_at, notes, checksum
			FROM {schema}.{tablename}
			WHERE project = {projectid}
			ORDER BY changed_at DESC
		""").format(schema=sql.Identifier(self.schema), tablename=sql.Identifier(TABLE_VERTICAL_SHARE),
					projectid=sql.Literal(self.project))
		return list(self.pgconn.get_query_data(query, False))

	def get_change_raw(self, changeid: str):
		query = sql.SQL("""
			SELECT content, checksum
			FROM {schema}.{tablename}
			WHERE project = {projectid} AND changeid = {changeid}
			ORDER BY changed_at DESC
		""").format(schema=sql.Identifier(self.schema), tablename=sql.Identifier(TABLE_VERTICAL_SHARE),
					projectid=sql.Literal(self.project), changeid=sql.Literal(changeid))
		return list(self.pgconn.get_query_data(query, False))[0]

	def delete_change(self, changeid: str):
		query = sql.SQL("""
			DELETE FROM {schema}.{tablename}
			WHERE project={projectid} AND changeid={changeid}
		""").format(schema=sql.Identifier(self.schema), tablename=sql.Identifier(TABLE_VERTICAL_SHARE),
					projectid=sql.Literal(self.project), changeid=sql.Literal(changeid))
		with closing(self._raw_conn()) as conn:
			with conn:
				with conn.cursor() as cur:
					cur.execute(query)

	def promote(self, changeid: str):
		query = sql.SQL("""
			UPDATE {schema}.{table_qgis} SET ( metadata, content ) = (
				SELECT {table_vertical}.metadata, {table_vertical}.content
				FROM {schema}.{table_vertical}
				WHERE project={projectid} AND changeid={changeid}
			) WHERE name={projectid}
		""").format(
			schema=sql.Identifier(self.schema), table_vertical=sql.Identifier(TABLE_VERTICAL_SHARE), table_qgis=sql.Identifier(TABLE_PROJECTS_QGIS),
			changeid=sql.Literal(changeid), projectid=sql.Literal(self.project)
		)
		with closing(self._raw_conn()) as conn:
			with conn:
				with conn.cursor() as cur:
					cur.execute(query)

	def get_latest_snapshot_hash(self):
		query = sql.SQL("""
			SELECT checksum FROM {schema}.{table_vertical}
			WHERE project = {projectname}
			ORDER BY changed_at DESC LIMIT 1
		""").format(schema=sql.Identifier(self.schema), table_vertical=sql.Identifier(TABLE_VERTICAL_SHARE),
					projectname=sql.Literal(self.project))
		rows = list(self.pgconn.get_query_data(query, False))
		return rows[0]["checksum"] if rows else None


# --------------------------------------------------------------------------- #
# GeoPackage (SQLite)
# --------------------------------------------------------------------------- #

def _as_bytes(value):
	"""content may come back from SQLite as bytes OR str (depending on the column
	affinity QGIS used): normalise to bytes for hashing / writing to disk."""
	if value is None:
		return None
	if isinstance(value, bytes):
		return value
	if isinstance(value, memoryview):
		return value.tobytes()
	if isinstance(value, str):
		return value.encode("utf-8")
	return bytes(value)


def _load_json(value) -> dict:
	if not value:
		return {}
	if isinstance(value, dict):
		return value
	try:
		return json.loads(value)
	except Exception:
		return {}

def _parse_dt(value) -> Optional[datetime.datetime]:
	if value is None or isinstance(value, datetime.datetime):
		return value
	text = str(value).replace("Z", "").replace("T", " ").strip()
	for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
		try:
			return datetime.datetime.strptime(text[:len("2026-06-19 11:59:00.000000")], fmt)
		except ValueError:
			continue
	return None


class GeoPackageBackend(ProjectBackend):

	# QGIS stores projects in a `qgis_projects` table inside the .gpkg, with
	# columns name/metadata/content (metadata is a JSON string).
	TABLE_QGIS = TABLE_PROJECTS_QGIS  # "qgis_projects"
	TABLE_HIST = TABLE_VERTICAL_SHARE

	def __init__(self, uri: str):
		self.path, self.project = self._parse_gpkg_uri(uri)
		# GeoPackage has no per-row author like PostgreSQL: fall back to the OS user
		try:
			self.username = getpass.getuser()
		except Exception:
			self.username = "qgis"

	@staticmethod
	def _parse_gpkg_uri(uri: str):
		# QGIS project URIs look like:
		#   geopackage:/home/me/data.gpkg?projectName=Foo       (Linux/macOS)
		#   geopackage:C:/Users/me/data.gpkg?projectName=Foo    (Windows)
		#   geopackage:/C:/Users/me/data.gpkg?projectName=Foo   (Windows, leading slash)
		body = uri.split(":", 1)[1] if ":" in uri else uri
		raw_path, _, query = body.partition("?")
		path = urllib.parse.unquote(raw_path)
		# strip a leading slash placed before a Windows drive letter ("/C:/..." -> "C:/...")
		if len(path) >= 3 and path[0] == "/" and path[1].isalpha() and path[2] == ":":
			path = path[1:]
		params = urllib.parse.parse_qs(query)
		project = (params.get("projectName") or params.get("project") or [None])[0]
		print("VerticalShare GeoPackage URI:", repr(uri), "-> path:", repr(path), "project:", repr(project))
		return path, project

	def _conn(self):
		# timeout lets writes wait if QGIS (or another session) holds the gpkg lock,
		# instead of failing immediately with "database is locked"
		try:
			conn = sqlite3.connect(self.path, timeout=30)
			conn.execute("PRAGMA busy_timeout = 30000")
			return conn
		except sqlite3.Error as ex:
			raise RuntimeError(
				"Cannot open the GeoPackage at '%s' (parsed from the project URI): %s" % (self.path, ex))

	def get_project_update_state(self):
		with closing(self._conn()) as conn:
			row = conn.execute(
				"SELECT content, metadata FROM %s WHERE name = ?" % self.TABLE_QGIS,
				(self.project,)).fetchone()
		if row is None:
			return None
		content, metadata = row[0], row[1]
		meta = _load_json(metadata)
		return ProjectUpdateState(
			content_hash=hashlib.md5(_as_bytes(content)).hexdigest() if content is not None else None,
			last_updated=self._meta_time(meta),
			last_author=meta.get("last_modified_user") or self.username,
		)

	def _meta_time(self, meta: dict):
		dt = _parse_dt(meta.get("last_modified_time"))
		if dt is not None:
			return dt
		try:  # fall back to the file modification time (UTC, to match the rest)
			return datetime.datetime.utcfromtimestamp(os.path.getmtime(self.path))
		except OSError:
			return None

	def has_history_table(self):
		with closing(self._conn()) as conn:
			row = conn.execute(
				"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
				(self.TABLE_HIST,)).fetchone()
		return row is not None

	def ensure_history_table(self):
		with closing(self._conn()) as conn:
			with conn:
				conn.execute("""CREATE TABLE IF NOT EXISTS %s (
					changeid	TEXT PRIMARY KEY,
					changename	TEXT,
					project		TEXT NOT NULL,
					content		BLOB NOT NULL,
					metadata	TEXT,
					changed_by	TEXT,
					changed_at	TEXT,
					notes		TEXT,
					checksum	TEXT
				)""" % self.TABLE_HIST)

	def save_snapshot(self, changename: str, notes: str):
		self.ensure_history_table()
		with closing(self._conn()) as conn:
			with conn:
				row = conn.execute(
					"SELECT content, metadata FROM %s WHERE name=?" % self.TABLE_QGIS,
					(self.project,)).fetchone()
				if row is None:
					raise RuntimeError("project '%s' not found in the geopackage" % self.project)
				content, metadata = row[0], row[1]
				meta = _load_json(metadata)
				conn.execute(
					"INSERT INTO %s (changeid, changename, project, content, metadata, changed_by, changed_at, notes, checksum) "
					"VALUES (?,?,?,?,?,?,?,?,?)" % self.TABLE_HIST,
					(
						str(uuid.uuid4()), changename, self.project, content, metadata,
						meta.get("last_modified_user") or self.username,
						meta.get("last_modified_time") or datetime.datetime.utcnow().isoformat(sep=" "),
						notes,
						hashlib.md5(_as_bytes(content)).hexdigest() if content is not None else None,
					))

	def get_history(self):
		with closing(self._conn()) as conn:
			cur = conn.execute(
				"SELECT changeid, changename, project, metadata, changed_by, changed_at, notes, checksum "
				"FROM %s WHERE project=? ORDER BY changed_at DESC" % self.TABLE_HIST,
				(self.project,))
			cols = [c[0] for c in cur.description]
			items = []
			for r in cur.fetchall():
				item = dict(zip(cols, r))
				item["metadata"] = _load_json(item.get("metadata"))
				item["changed_at"] = _parse_dt(item.get("changed_at"))
				items.append(item)
			return items

	def get_change_raw(self, changeid: str):
		with closing(self._conn()) as conn:
			row = conn.execute(
				"SELECT content, checksum FROM %s WHERE project=? AND changeid=?" % self.TABLE_HIST,
				(self.project, changeid)).fetchone()
		return {"content": _as_bytes(row[0]), "checksum": row[1]}

	def delete_change(self, changeid: str):
		with closing(self._conn()) as conn:
			with conn:
				conn.execute(
					"DELETE FROM %s WHERE project=? AND changeid=?" % self.TABLE_HIST,
					(self.project, changeid))

	def promote(self, changeid: str):
		with closing(self._conn()) as conn:
			with conn:
				row = conn.execute(
					"SELECT content, metadata FROM %s WHERE project=? AND changeid=?" % self.TABLE_HIST,
					(self.project, changeid)).fetchone()
				if row is None:
					raise RuntimeError("snapshot not found")
				conn.execute(
					"UPDATE %s SET content=?, metadata=? WHERE name=?" % self.TABLE_QGIS,
					(row[0], row[1], self.project))

	def get_latest_snapshot_hash(self):
		if not self.has_history_table():
			return None
		with closing(self._conn()) as conn:
			row = conn.execute(
				"SELECT checksum FROM %s WHERE project=? ORDER BY changed_at DESC LIMIT 1" % self.TABLE_HIST,
				(self.project,)).fetchone()
		return row[0] if row else None
