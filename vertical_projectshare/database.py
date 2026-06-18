import urllib.parse
from typing import Dict, List, Generator, TypeVar, TypedDict, Tuple

import psycopg2.extras
from psycopg2 import sql
from psycopg2._psycopg import connection
from psycopg2.sql import SQL, Composed
from qgis._core import QgsAbstractDatabaseProviderConnection, QgsDataSourceUri

T = TypeVar("T")

class DbColumnDefinition (TypedDict):

	table_catalog:          str
	table_schema:           str
	table_name:             str
	column_name:            str
	data_type:              str
	udt_name:               str

class PgConnector:

	CONNS: Dict[str, "PgConnector"] = {}

	@staticmethod
	def get_conn (connstr: str):
		if connstr not in PgConnector.CONNS:
			PgConnector.CONNS[connstr] = PgConnector(connstr)
		return PgConnector.CONNS[connstr]

	@staticmethod
	def from_qconn (conn: QgsAbstractDatabaseProviderConnection):
		return PgConnector.get_conn(PgConnector.get_dbconn_string(conn))


	def __init__ (self, connstring: str):
		# self.pooler = SimpleConnectionPool(2,4, connstring)
		self.connstr = connstring

	@staticmethod
	def get_postgres_connstring(host: str, port: int, dbname: str, user: str, password: str, schema: str = None):

		connstring = "postgresql://{username}:{password}@{host}:{port}?dbname={database}".format(
			username=urllib.parse.quote_plus(user),
			password=urllib.parse.quote_plus(password),
			host=host,
			port=port,
			database=dbname
		)

		if schema is not None:
			connstring += "&schema=" + schema

		return connstring

	@staticmethod
	def get_dbconn_string (conn: QgsAbstractDatabaseProviderConnection, schema: str = None):
		uristring = conn.uri()
		uridict = dict(part.split("=") for part in uristring.split())
		for key, value in uridict.items():
			if value.startswith("'") and value.endswith("'"):
				uridict[key] = value[1:-1]
		if schema is not None:
			uridict["schema"] = schema
		return PgConnector.get_postgres_connstring(**uridict)

	def get_query_data (self, query: SQL|Composed, debug: bool = False) -> Generator[T, None, None]:
		# with self.pooler.getconn() as conn:  # type: connection
		with connection(self.connstr) as conn:
			with conn.cursor(cursor_factory = psycopg2.extras.DictCursor) as cur:
				if debug:
					print("QUERY DEBUG: " + query.as_string(cur))
				cur.execute(query)
				data = cur.fetchone()
				while data is not None:
					datadict = {}
					for key, val in data.items():
						datadict[key] = val
					yield datadict
					data = cur.fetchone()

	def get_table_columns (self, schema: str, table: str) -> List[DbColumnDefinition]:

		query = sql.SQL("""
			SELECT table_catalog, table_schema, table_name, column_name, data_type, udt_name
			FROM information_schema.columns
			WHERE table_schema = {schema} AND table_name = {table}
		""").format(schema=sql.Literal(schema), table=sql.Literal(table))

		coldefs: List[DbColumnDefinition] = []
		for item in self.get_query_data(query):
			coldefs.append(item)
		return coldefs

	def execute_alter_query (self, query: SQL|Composed, debug: bool = False) -> Tuple[int, str]:
		# with self.pooler.getconn() as conn: # type: connection
		with connection(self.connstr) as conn:
			with conn.cursor() as cur:
				if debug:
					print("QUERY DEBUG: " + query.as_string(cur))
				cur.execute(query)
				return cur.rowcount, cur.statusmessage

