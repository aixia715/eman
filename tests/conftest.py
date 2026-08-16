import pytest
from fastapi.testclient import TestClient

from eman.main import create_app


@pytest.fixture()
def client():
    app = create_app(":memory:")
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def make_experiment(client):
    def _make(**over):
        body = {
            "name": "示例实验",
            "purpose": "验证输出随温度的变化",
            "method": "控制变量法",
            "independent_vars": [{"name": "温度/℃", "default": "25"}],
            "dependent_vars": ["电压/V"],
            "category_tags": ["示例"],
        }
        body.update(over)
        r = client.post("/api/experiments", json=body)
        assert r.status_code == 201, r.text
        return r.json()
    return _make


@pytest.fixture()
def make_run(client, make_experiment):
    def _make(experiment_id=None, name="第一次执行"):
        if experiment_id is None:
            experiment_id = make_experiment()["id"]
        r = client.post(f"/api/experiments/{experiment_id}/runs", json={"name": name})
        assert r.status_code == 201, r.text
        return r.json()
    return _make


@pytest.fixture()
def make_group(client, make_run):
    def _make(run_id=None, variable_values=None):
        if run_id is None:
            run_id = make_run()["id"]
        if variable_values is None:
            variable_values = client.get(
                f"/api/runs/{run_id}/new-group-template").json()["variable_values"]
        r = client.post(f"/api/runs/{run_id}/groups",
                        json={"variable_values": variable_values})
        assert r.status_code == 201, r.text
        return r.json()
    return _make


@pytest.fixture()
def make_attempt(client, make_group):
    def _make(group_id=None):
        if group_id is None:
            group_id = make_group()["id"]
        r = client.post(f"/api/groups/{group_id}/attempts")
        assert r.status_code == 201, r.text
        return r.json()
    return _make
