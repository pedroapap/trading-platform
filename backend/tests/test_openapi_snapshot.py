"""The frontend's API types are generated from a snapshot of the schema, which must be current."""

import json
from pathlib import Path

from app import cli
from app.main import app

SNAPSHOT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "openapi.json"


def test_the_frontend_has_the_current_api_schema():
    assert json.loads(SNAPSHOT.read_text()) == app.openapi(), "The API changed: run `make openapi`"


def test_the_cli_prints_the_schema(capsys):
    assert cli.main(["openapi"]) == 0

    assert json.loads(capsys.readouterr().out) == app.openapi()
