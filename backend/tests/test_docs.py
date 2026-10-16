"""The docs are checked like code: every relative link and image leads to a file (and heading)
that exists, every example strategy (a ```json strategy block) is a valid definition, every
endpoint they name ("GET /api/trades") is one the API has, and the data model page lists the
columns the migrations build."""

import json
import re
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import text

from app.main import app
from app.strategies.definition import StrategyDefinition

ROOT = Path(__file__).resolve().parents[2]
PAGES = sorted(
    page
    for page in [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
    if page.exists() and "node_modules" not in page.parts
)

FENCE = re.compile(r"^(```|~~~).*?^\1", re.M | re.S)
LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.M)
STRATEGY = re.compile(r"^```json strategy\n(.*?)^```", re.M | re.S)
ENDPOINT = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE) (/api/[^\s`)?#]*)")


def name(page: Path) -> str:
    return str(page.relative_to(ROOT))


def prose(page: Path) -> str:
    """The page without its code blocks, where links are only examples."""
    return FENCE.sub("", page.read_text())


def anchors(page: Path) -> set[str]:
    """The heading anchors GitHub makes: lowercase, punctuation dropped, spaces as hyphens,
    and -1, -2… after repeats."""
    seen: Counter[str] = Counter()
    found = set()
    for heading in HEADING.findall(prose(page)):
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # a link's text only
        slug = re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")
        found.add(f"{slug}-{seen[slug]}" if seen[slug] else slug)
        seen[slug] += 1
    return found


def links() -> list[tuple[Path, str]]:
    return [
        (page, target)
        for page in PAGES
        for target in LINK.findall(prose(page))
        if not re.match(r"[a-z][a-z0-9+.-]*:", target)  # not https:, mailto:…
    ]


@pytest.mark.parametrize(("page", "target"), links(), ids=[f"{name(p)} -> {t}" for p, t in links()])
def test_a_relative_link_leads_somewhere(page, target):
    path, _, anchor = target.partition("#")
    linked = (page.parent / path).resolve() if path else page
    assert linked.exists(), f"{name(page)} links to {target}, which doesn't exist"
    if anchor and linked.suffix == ".md":
        assert anchor in anchors(linked), f"{name(linked)} has no heading #{anchor}"


def strategies() -> list[tuple[Path, int, str]]:
    return [
        (page, number, block)
        for page in PAGES
        for number, block in enumerate(STRATEGY.findall(page.read_text()), 1)
    ]


@pytest.mark.parametrize(
    ("page", "number", "block"),
    strategies(),
    ids=[f"{name(p)} strategy {n}" for p, n, _ in strategies()],
)
def test_an_example_strategy_is_a_valid_definition(page, number, block):
    StrategyDefinition.model_validate(json.loads(block))


def _route(path: str) -> str:
    """The path with its parameters' names dropped: /api/trades/{} for /api/trades/{id}."""
    return re.sub(r"\{[^}]*\}", "{}", path.rstrip("/"))


ROUTES = {
    (method.upper(), _route(path))
    for path, operations in app.openapi()["paths"].items()
    for method in operations
}


def endpoints() -> list[tuple[Path, str, str]]:
    return sorted(
        {
            (page, method, path)
            for page in PAGES
            for method, path in ENDPOINT.findall(page.read_text())
        }
    )


@pytest.mark.parametrize(
    ("page", "method", "path"),
    endpoints(),
    ids=[f"{name(p)} {m} {path}" for p, m, path in endpoints()],
)
def test_a_named_endpoint_exists(page, method, path):
    assert (method, _route(path)) in ROUTES, f"{name(page)} names {method} {path}"


SCHEMA = ROOT / "docs" / "schema.md"
TABLE = re.compile(r"^### `(\w+)`\n(.*?)(?=^#{1,3} |\Z)", re.M | re.S)
COLUMN = re.compile(r"^\| `(\w+)` \| `([^`]+)` \|([^|]*)\|([^|]*)\|", re.M)
# What `\d+` shows: each column's type, whether it is "not null", and its default.
BUILT = text(
    """
    SELECT c.table_name, c.column_name, format_type(a.atttypid, a.atttypmod),
           c.is_nullable, c.column_default, c.identity_generation
    FROM information_schema.columns c
    JOIN pg_attribute a
      ON a.attrelid = format('%I.%I', c.table_schema, c.table_name)::regclass
     AND a.attname = c.column_name
    WHERE c.table_schema = 'public'
    ORDER BY c.table_name, c.ordinal_position
    """
)


def _short(type_: str) -> str:
    return type_.replace("character varying", "varchar").replace(
        "timestamp with time zone", "timestamptz"
    )


def _default(default: str | None, identity: str | None) -> str:
    """The default as the page writes it: `'open'` for `'open'::character varying`."""
    if identity:
        return f"generated {identity.lower()} as identity"
    return re.sub(r"::[a-z ]+(\[\])?", "", default or "")


def test_the_data_model_page_lists_the_columns_the_migrations_build(engine):
    with engine.connect() as connection:
        rows = connection.execute(BUILT).all()
    built: dict[str, list[tuple[str, ...]]] = {}
    for table, column, type_, nullable, default, identity in rows:
        null = "not null" if nullable == "NO" else ""
        built.setdefault(table, []).append(
            (column, _short(type_), null, _default(default, identity))
        )
    documented = {
        table: [
            (column, type_, null.strip(), default.strip().strip("`"))
            for column, type_, null, default in COLUMN.findall(section)
        ]
        for table, section in TABLE.findall(SCHEMA.read_text())
    }
    assert sorted(documented) == sorted(built)
    for table, columns in built.items():
        assert documented[table] == columns, f"docs/schema.md's {table} isn't the database's"


def test_the_docs_are_found():
    assert ROOT / "docs" / "sample-data" / "README.md" in PAGES
