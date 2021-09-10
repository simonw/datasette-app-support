from datasette.database import Database
from datasette.utils.asgi import Response, Forbidden
from datasette.utils import sqlite3
from datasette import hookimpl
from sqlite_utils.utils import rows_from_file
import json
import os
import pathlib
import secrets
import sqlite_utils


@hookimpl
def startup(datasette):
    datasette.remove_database("_memory")
    datasette.add_memory_database("temporary")


@hookimpl
def permission_allowed(actor, action, resource):
    # Block access to _internal even for the "root" actor
    if action == "view-database" and resource == "_internal":
        return False


unauthorized = Response.json({"ok": False, "error": "Not authorized"}, status=401)


@hookimpl
def extra_css_urls(datasette):
    return [datasette.urls.static_plugins("datasette_app_support", "sticky-footer.css")]


def check_auth(request):
    env_token = os.environ.get("DATASETTE_API_TOKEN")
    request_token = request.headers.get("authorization", "").replace("Bearer ", "")
    if not env_token or not request_token:
        return False
    return secrets.compare_digest(
        request_token,
        env_token,
    )


async def open_database_file(request, datasette):
    if not check_auth(request):
        return unauthorized
    try:
        filepath = await _filepath_from_json_body(request)
    except PathError as e:
        return Response.json({"ok": False, "error": e.message}, status=400)
    # Confirm it's a valid SQLite database
    conn = sqlite3.connect(filepath)
    try:
        conn.execute("select * from sqlite_master")
    except sqlite3.DatabaseError:
        return Response.json(
            {"ok": False, "error": "Not a valid SQLite database"}, status=400
        )
    # Is that file already open?
    existing_paths = {
        pathlib.Path(db.path).resolve()
        for db in datasette.databases.values()
        if db.path
    }
    if pathlib.Path(filepath).resolve() in existing_paths:
        return Response.json(
            {"ok": False, "error": "That file is already open"}, status=400
        )
    added_db = datasette.add_database(
        Database(datasette, path=filepath, is_mutable=True)
    )
    return Response.json({"ok": True, "path": datasette.urls.database(added_db.name)})


async def new_empty_database_file(request, datasette):
    if not check_auth(request):
        return unauthorized
    try:
        filepath = await _filepath_from_json_body(request, must_exist=False)
    except PathError as e:
        return Response.json({"ok": False, "error": e.message}, status=400)
    # File should not exist yet
    if os.path.exists(filepath):
        return Response.json(
            {"ok": False, "error": "That file already exists"}, status=400
        )

    conn = sqlite3.connect(filepath)
    conn.execute("vacuum")

    added_db = datasette.add_database(
        Database(datasette, path=filepath, is_mutable=True)
    )
    return Response.json({"ok": True, "path": datasette.urls.database(added_db.name)})


class PathError(Exception):
    def __init__(self, message):
        self.message = message


async def _filepath_from_json_body(request, must_exist=True, return_data=False):
    body = await request.post_body()
    try:
        data = json.loads(body)
    except ValueError:
        raise PathError("Invalid request body, should be JSON")
    filepath = data.get("path")
    if not filepath:
        raise PathError("'path' key is required'")
    if must_exist and not os.path.exists(filepath):
        raise PathError("'path' does not exist")
    if return_data:
        return filepath, data
    else:
        return filepath


async def open_csv_file(request, datasette):
    return await _import_csv_file(request, datasette, database="temporary")


async def import_csv_file(request, datasette):
    return await _import_csv_file(request, datasette)


async def _import_csv_file(request, datasette, database=None):
    if not check_auth(request):
        return unauthorized
    try:
        filepath, body = await _filepath_from_json_body(request, return_data=True)
    except PathError as e:
        return Response.json({"ok": False, "error": e.message}, status=400)

    if database is None:
        database = body.get("database")
    if not database or database not in datasette.databases:
        return Response.json({"ok": False, "error": "Invalid database"}, status=400)

    db = datasette.get_database(database)

    # Derive a table name
    table_name = pathlib.Path(filepath).stem
    root_table_name = table_name
    i = 1
    while await db.table_exists(table_name):
        table_name = "{}_{}".format(root_table_name, i)
        i += 1

    try:
        rows = rows_from_file(open(filepath, "rb"))[0]

        def write_rows(conn):
            dbconn = sqlite_utils.Database(conn)
            dbconn[table_name].insert_all(rows)
            return dbconn[table_name].count

        num_rows = await db.execute_write_fn(write_rows, block=True)
        return Response.json(
            {
                "ok": True,
                "path": datasette.urls.table(database, table_name),
                "rows": num_rows,
            }
        )
    except Exception as e:
        return Response.json({"ok": False, "error": str(e)}, status=500)


async def auth_app_user(request, datasette):
    if not check_auth(request):
        return unauthorized
    body = await request.post_body()
    try:
        data = json.loads(body)
    except ValueError:
        data = {}
    redirect = data.get("redirect") or "/"
    response = Response.redirect(redirect)
    response.set_cookie("ds_actor", datasette.sign({"a": {"id": "root"}}, "actor"))
    return response


async def dump_temporary_to_file(request, datasette):
    if not check_auth(request):
        return unauthorized
    try:
        filepath = await _filepath_from_json_body(request, must_exist=False)
    except PathError as e:
        return Response.json({"ok": False, "error": e.message}, status=400)
    db = datasette.get_database("temporary")

    def backup(conn):
        conn.isolation_level = None
        conn.execute("vacuum into '{}'".format(filepath))
        conn.isolation_level = ""

    await db.execute_write_fn(backup, block=True)
    return Response.json({"ok": True, "path": filepath})


async def restore_temporary_from_file(request, datasette):
    if not check_auth(request):
        return unauthorized
    try:
        filepath = await _filepath_from_json_body(request)
    except PathError as e:
        return Response.json({"ok": False, "error": e.message}, status=400)
    temporary = datasette.get_database("temporary")
    backup_db = sqlite3.connect(filepath, uri=True)
    temporary_conn = temporary.connect(write=True)
    backup_db.backup(temporary_conn)
    backup_tables = [
        r[0]
        for r in backup_db.execute(
            "select name from sqlite_master where type='table'"
        ).fetchall()
    ]
    temporary_conn.close()
    backup_db.close()
    return Response.json(
        {
            "ok": True,
            "path": filepath,
            "restored_tables": await temporary.table_names(),
            "backup_tables": backup_tables,
        }
    )


@hookimpl
def register_routes():
    return [
        (r"^/-/open-database-file$", open_database_file),
        (r"^/-/new-empty-database-file$", new_empty_database_file),
        (r"^/-/open-csv-file$", open_csv_file),
        (r"^/-/import-csv-file$", import_csv_file),
        (r"^/-/auth-app-user$", auth_app_user),
        (r"^/-/dump-temporary-to-file$", dump_temporary_to_file),
        (r"^/-/restore-temporary-from-file$", restore_temporary_from_file),
    ]
