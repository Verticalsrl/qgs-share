import time
from abc import ABC
from contextlib import closing
from typing import Dict, TypedDict, NamedTuple, Optional
import datetime

# qgis.PyQt re-exports PyQt5 on QGIS 3 (Qt5) and PyQt6 on QGIS 4 (Qt6): same code, both versions
from qgis.PyQt.QtCore import QObject, pyqtSlot, pyqtSignal, QThread
import psycopg2
from psycopg2 import sql

from .project_connector import ProjectUpdateState, DbProjectConnector
from .constants import TABLE_VERTICAL_SHARE, TABLE_PROJECTS_QGIS



class HistoryDataItem (TypedDict):
	changeid:				str
	changename:				str
	project:				str
	metadata:				Dict
	changed_by:				str
	changed_at:				datetime.datetime
	notes:					str
	checksum:				str


class SnapShooterListener (ABC):

	def on_state_update_check(self, collected_at: float, state: ProjectUpdateState):
		raise NotImplementedError


class VerticalShareSnapper:

	INSTANCES: Dict[str, "VerticalShareSnapper"] = {}

	@staticmethod
	def get_for (uri: str):
		if uri not in VerticalShareSnapper.INSTANCES:
			VerticalShareSnapper.INSTANCES[uri] = VerticalShareSnapper(uri)
		return VerticalShareSnapper.INSTANCES[uri]

	def __init__(self, uri: str):
		self.project_connector = DbProjectConnector(uri)
		# self.connector = PgConnector.get_conn(self.project_connector.parsed_uri.connstr)
		# kinda redundant but we can keep the old code as is until we optimize a bit
		self.parsed_uri = self.project_connector.parsed_uri
		self.connector = self.project_connector.pgconn

		self.watcher_worker: ProjectStatePollerWorker = None
		self.watcher_thread: QThread = None

		self.listener: SnapShooterListener = None

	def get_conn(self):
		return psycopg2.connect(self.connector.connstr)

	def get_live_project_update_state (self):
		return self.project_connector.get_project_update_state()

	def get_latest_snaphost_hash(self):
		query = sql.SQL("""
			SELECT {table_vertical}.checksum
			FROM {schema}.{table_vertical}
			WHERE {table_vertical}.project = {projectname}
			ORDER BY {table_vertical}.changed_at DESC
			LIMIT 1
		""").format(
			schema=sql.Identifier(self.parsed_uri.schema), table_vertical=sql.Identifier(TABLE_VERTICAL_SHARE),
			projectname=sql.Literal(self.parsed_uri.project)
		)

		rows = list(self.connector.get_query_data(query, False))
		if len(rows) > 0:
			return rows[0]["checksum"]
		else:
			return None

	def ensure_history_schema_table(self):
		if not self.has_schema_tables():
			print("creating missing table for schema %s" % self.parsed_uri.schema)
			self.prepare_history_table()

	def save_project_snapshot(self, changename: str, notes: str):
		print("checking for schema tables")
		self.ensure_history_schema_table()

		print("saving data to history table")

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
			schema=sql.Identifier(self.parsed_uri.schema), table_vertical=sql.Identifier(TABLE_VERTICAL_SHARE), table_qgis=sql.Identifier(TABLE_PROJECTS_QGIS),
			changename=sql.Literal(changename), notes=sql.Literal(notes), changedby=sql.Literal(self.parsed_uri.username),
			projectname=sql.Literal(self.parsed_uri.project)
		)

		with closing(self.get_conn()) as conn:
			with conn:
				with conn.cursor() as cur:
					print(query.as_string(cur))
					cur.execute(query)

					print("data saved")

	def has_schema_tables(self):
		cols = self.connector.get_table_columns(self.parsed_uri.schema, TABLE_VERTICAL_SHARE)
		# TODO: make a better check when the creator is stable
		return len(cols) > 0

	def get_history_data (self):
		query = sql.SQL("""
			SELECT
				changeid,
				changename,
				project,
				metadata,
				changed_by,
				changed_at,
				notes,
				checksum
			FROM {schema}.{tablename}
			WHERE project = {projectid}
			ORDER BY changed_at DESC
		""").format(schema=sql.Identifier(self.parsed_uri.schema), tablename=sql.Identifier(TABLE_VERTICAL_SHARE),
					projectid=sql.Literal(self.parsed_uri.project))
		return list(self.connector.get_query_data(query, False))

	def prepare_history_table (self):

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
		)""").format(schema=sql.Identifier(self.parsed_uri.schema), tablename=sql.Identifier(TABLE_VERTICAL_SHARE))

		with closing(self.get_conn()) as conn:
			with conn:
				with conn.cursor() as cur:
					cur.execute(query)

	def get_change_data_raw(self, changeid: str):
		query = sql.SQL("""
			SELECT
				content,
				checksum
			FROM {schema}.{tablename}
			WHERE
				project = {projectid} AND
				changeid = {changeid}
			ORDER BY changed_at DESC
		""").format(schema=sql.Identifier(self.parsed_uri.schema), tablename=sql.Identifier(TABLE_VERTICAL_SHARE),
					projectid=sql.Literal(self.parsed_uri.project), changeid=sql.Literal(changeid))
		return list(self.connector.get_query_data(query, False))[0]


	def delete_change(self, changeid: str):

		query = sql.SQL("""
			DELETE FROM {schema}.{tablename}
			WHERE
				project={projectid} AND changeid={changeid}
		""").format(
			schema=sql.Identifier(self.parsed_uri.schema), tablename=sql.Identifier(TABLE_VERTICAL_SHARE),
			projectid=sql.Literal(self.parsed_uri.project), changeid=sql.Literal(changeid)
		)

		with closing(self.get_conn()) as conn:
			with conn:
				with conn.cursor() as cur:
					cur.execute(query)

	def on_project_polled (self, ts: float, data: ProjectUpdateState):
		print("project polled at ", ts, data)
		if self.listener is not None:
			self.listener.on_state_update_check(ts, data)

	def start_watch (self):
		if self.watcher_worker is None:
			self.watcher_thread = QThread()
			self.watcher_worker = ProjectStatePollerWorker(self)
			self.watcher_worker.moveToThread(self.watcher_thread)
			self.watcher_worker.on_polling_update.connect(self.on_project_polled)
			self.watcher_thread.start()
			self.watcher_worker.trigger_start.emit()
			print("launched watcher thread ", self.watcher_thread, "worker", self.watcher_worker)
		else:
			print("watcher already running")

	def end_watch (self):

		# FIRST you ALWAYS stop the worker

		if self.watcher_worker is not None:
			print("trying to soft-stop the worker")
			self.watcher_worker.trigger_stop.emit()
		else:
			print("alread stopped worker ", self.watcher_worker, "on", self.watcher_thread)

		if self.watcher_thread is not None:
			print("quitting signal thread")
			# self.signal_thread.finished.emit()
			self.watcher_thread.quit()
			self.watcher_thread.wait()
			self.watcher_thread = None
		else:
			print("no signal thread running")

		self.watcher_worker = None

	def poll_once (self):
		if self.watcher_worker is not None:
			self.watcher_worker.poll_once()

	def promote_snapshot (self, changeid: str):
		query = sql.SQL("""
			UPDATE {schema}.{table_qgis} SET( metadata, content ) = (
				SELECT
					{table_vertical}.metadata,
					{table_vertical}.content
				FROM {schema}.{table_vertical}
				WHERE project={projectid} AND changeid={changeid}
			) WHERE name={projectid}
		""").format(
			schema=sql.Identifier(self.parsed_uri.schema), table_vertical=sql.Identifier(TABLE_VERTICAL_SHARE), table_qgis=sql.Identifier(TABLE_PROJECTS_QGIS),
			changeid=sql.Literal(changeid), projectid=sql.Literal(self.parsed_uri.project)
		)

		with closing(self.get_conn()) as conn:
			with conn:
				with conn.cursor() as cur:
					print(query.as_string(cur))
					cur.execute(query)

					print("data saved")


class ProjectStatePollerWorker (QObject):

	on_polling_update = pyqtSignal(float, dict)  # timestamp, data
	is_running: bool

	trigger_start = pyqtSignal()
	trigger_stop = pyqtSignal()

	def __init__(self, master: "VerticalShareSnapper"):
		super().__init__()
		self.is_running = False
		self.master = master
		self.wait_time = 60
		self.trigger_start.connect(self.start_run)
		self.trigger_stop.connect(self.end_run_clean)

	# NOTE: starter signal callback MUST have pyqtSlot to avoid being blocking
	# ender signal callback MUST NOT have pyqtSlot

	@pyqtSlot()
	def start_run(self, *args, **kwargs):
		print("received start signal", args, kwargs)
		if not self.is_running:
			self.poll_and_wait()
		else:
			print("already running wait_and_signal")

	def end_run_clean (self, *args, **kwargs):
		print("received end signal", args, kwargs)
		if self.is_running:
			self.is_running = False
		else:
			print("already stopped I suppose")

	def breakable_wait_cycle (self,):
		to_wait = self.wait_time
		for i in range(0, to_wait):
			if self.is_running:
				time.sleep(1)
			else:
				break

	def poll_and_wait(self):
		print("polling every %d seconds" % self.wait_time)
		self.is_running = True
		while self.is_running:
			update_state: ProjectUpdateState = self.master.get_live_project_update_state()
			ctimestamp = time.time()
			self.on_polling_update.emit(ctimestamp, update_state)
			self.breakable_wait_cycle()
		print("polling finished")

	def poll_once (self):
		update_state: ProjectUpdateState = self.master.get_live_project_update_state()
		ctimestamp = time.time()
		self.on_polling_update.emit(ctimestamp, update_state)
