from datasette.app import Datasette
import pytest


@pytest.mark.asyncio
async def test_open_csv_files(tmpdir):
    datasette = Datasette([], memory=True)
    await datasette.invoke_startup()
    path = str(tmpdir / "demo.csv")
    open(path, "w").write("id,name\n123,Hello")
    response = await datasette.client.post("/-/open-csv-file", json={"path": path})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    response = await datasette.client.get("/temporary/demo.json?_shape=array")
    assert response.json() == [{"rowid": 1, "id": "123", "name": "Hello"}]
