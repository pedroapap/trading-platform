"""The docs are checked like code: every relative link and image leads to a file (and heading)
that exists, every example strategy (a ```json strategy block) is a valid definition, and
every endpoint they name ("GET /api/trades") is one the API has."""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

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


def test_the_docs_are_found():
    assert ROOT / "docs" / "sample-data" / "README.md" in PAGES
