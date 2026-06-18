import datetime
import urllib.parse
from typing import TypedDict, NamedTuple

from psycopg2 import sql

from .constants import TABLE_PROJECTS_QGIS
from .database import PgConnector


class ParsedDbUri (NamedTuple):
	connstr:				str
	username:				str
	schema:					str
	project:				str

class ProjectUpdateState (TypedDict):
	content_hash:			str
	last_updated:			datetime.datetime
	last_author:			str

class DbProjectConnector:

	def __init__(self, project_uri: str):
		self.project_uri = project_uri
		self.parsed_uri = DbProjectConnector.parse_db_uri(project_uri)
		self.pgconn = PgConnector.get_conn(self.parsed_uri.connstr)

	@staticmethod
	def parse_db_uri(uri: str) -> ParsedDbUri:
		parsed = urllib.parse.urlparse(uri)
		queryparams = urllib.parse.parse_qs(parsed.query)
		connstr = "%s://%s?dbname=%s" % (parsed.scheme, parsed.netloc, queryparams["dbname"][0])
		dbschema = queryparams.get("schema", [None])[0]
		project = queryparams.get("project", [None])[0]
		return ParsedDbUri(connstr, parsed.username, dbschema, project)

	def get_project_update_state (self) -> ProjectUpdateState:
		query = sql.SQL("""
			SELECT md5({table_qgis}.content) as content_hash,
				(metadata->>'last_modified_time')::TIMESTAMP AS last_updated,
				metadata->>'last_modified_user' AS last_author
			FROM {schema}.{table_qgis}
			WHERE {table_qgis}.name = {projectname}
		""").format(
			schema=sql.Identifier(self.parsed_uri.schema), table_qgis=sql.Identifier(TABLE_PROJECTS_QGIS),
			projectname=sql.Literal(self.parsed_uri.project)
		)

		rows = list(self.pgconn.get_query_data(query, False))
		return rows[0] if len(rows) == 1 else None

