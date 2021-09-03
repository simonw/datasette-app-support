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
def extra_css_urls(datasette):
    return [datasette.urls.static_plugins("datasette_app_support", "sticky-footer.css")]


async def open_database_file(request, datasette):
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


class PathError(Exception):
    def __init__(self, message):
        self.message = message


async def _filepath_from_json_body(request):
    body = await request.post_body()
    try:
        data = json.loads(body)
    except ValueError:
        raise PathError("Invalid request body, should be JSON")
    filepath = data.get("path")
    if not filepath:
        raise PathError("'path' key is required'")
    if not os.path.exists(filepath):
        raise PathError("'path' does not exist")
    return filepath


async def open_csv_file(request, datasette):
    try:
        filepath = await _filepath_from_json_body(request)
    except PathError as e:
        return Response.json({"ok": False, "error": e.message}, status=400)

    db = datasette.get_database("temporary")

    # Derive a table name
    table_name = pathlib.Path(filepath).stem
    root_table_name = table_name
    i = 1
    while await db.table_exists(table_name):
        table_name = "{}_{}".format(root_table_name, i)
        i += 1

    # TODO: verify file is valid
    rows = rows_from_file(open(filepath, "rb"))[0]

    def write_rows(conn):
        dbconn = sqlite_utils.Database(conn)
        dbconn[table_name].insert_all(rows)
        return dbconn[table_name].count

    num_rows = await db.execute_write_fn(write_rows, block=True)
    return Response.json(
        {
            "ok": True,
            "path": datasette.urls.table("temporary", table_name),
            "rows": num_rows,
        }
    )


async def auth_token_persistent(request, datasette):
    token = request.args.get("token") or ""
    if not datasette._root_token:
        raise Forbidden("Root token has already been used")
    if secrets.compare_digest(token, datasette._root_token):
        datasette._root_token = None
        response = Response.redirect(datasette.urls.instance())
        response.set_cookie(
            "ds_actor",
            datasette.sign({"a": {"id": "root"}}, "actor"),
            expires=364 * 24 * 60 * 60,
        )
        print(response._set_cookie_headers)
        return response
    else:
        raise Forbidden("Invalid token")


@hookimpl
def register_routes():
    return [
        (r"^/-/open-database-file$", open_database_file),
        (r"^/-/open-csv-file$", open_csv_file),
        (r"^/-/auth-token-persistent$", auth_token_persistent),
    ]
