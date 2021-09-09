from datasette.app import Datasette
import pytest
import sqlite3


@pytest.mark.asyncio
async def test_dump_restore_temporary(tmpdir):
    datasette = Datasette([], memory=True)
    await datasette.invoke_startup()
    # Import CSV into temporary
    path = str(tmpdir / "backup_demo.csv")
    backup_path = str(tmpdir / "backup.db")
    open(path, "w").write("id,name\n123,Hello")
    response = await datasette.client.post(
        "/-/open-csv-file",
        json={"path": path},
        headers={"Authorization": "Bearer fake-token"},
    )
    assert response.status_code == 200
    # Dump temporary to a file
    response = await datasette.client.post(
        "/-/dump-temporary-to-file",
        json={"path": backup_path},
        headers={"Authorization": "Bearer fake-token"},
        allow_redirects=False,
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "path": backup_path}
    # Check that the backup file has the right stuff
    conn = sqlite3.connect(backup_path)
    assert conn.execute("select * from backup_demo").fetchall() == [("123", "Hello")]
