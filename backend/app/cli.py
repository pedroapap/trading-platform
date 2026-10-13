"""Admin commands, e.g. `python -m app.cli create-user --email you@example.com`."""

import argparse
import getpass
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.errors import DomainError
from app.market_data import formats
from app.market_data.timeframes import Timeframe
from app.schemas.auth import RegisterRequest
from app.services import market_data, users

SHOWN_REJECTIONS = 20


@contextmanager
def session_scope() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    return password


def create_user(args: argparse.Namespace) -> int:
    try:
        account = RegisterRequest(email=args.email, password=_read_password(args.password_stdin))
    except ValidationError as exc:
        for error in exc.errors():
            print(f"{error['loc'][0]}: {error['msg']}", file=sys.stderr)
        return 1
    with session_scope() as db:
        try:
            user = users.create_user(db, account.email, account.password)
        except users.EmailTakenError:
            print(f"A user with email {account.email} already exists", file=sys.stderr)
            return 1
        print(f"Created user {user.email} ({user.id})")
    return 0


def import_csv(args: argparse.Namespace) -> int:
    try:
        with (
            open(args.path, encoding="utf-8-sig", newline="") as stream,
            session_scope() as db,
        ):
            summary = market_data.import_bars(db, stream, args.symbol, args.timeframe, args.format)
    except OSError as exc:
        print(f"Cannot read {args.path}: {exc.strerror}", file=sys.stderr)
        return 1
    except DomainError as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Imported {summary.inserted} {summary.timeframe} bars for {summary.symbol}"
        f" ({summary.format}): {summary.duplicates} already stored,"
        f" {summary.rejected} rows rejected"
    )
    if summary.first_ts is not None:
        print(f"Bars in file: {summary.first_ts.isoformat()} to {summary.last_ts.isoformat()}")
    for rejection in summary.rejections[:SHOWN_REJECTIONS]:
        print(f"  line {rejection.line}: {rejection.reason}")
    if summary.rejected > SHOWN_REJECTIONS:
        print(f"  ... and {summary.rejected - SHOWN_REJECTIONS} more")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="create a login account")
    create.add_argument("--email", required=True)
    create.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from stdin instead of prompting",
    )
    create.set_defaults(handler=create_user)

    importer = commands.add_parser("import-csv", help="import a price file into market data")
    importer.add_argument("path")
    importer.add_argument("--symbol", required=True)
    importer.add_argument(
        "--timeframe",
        type=Timeframe,
        choices=list(Timeframe),
        help="bar size (inferred from the data if omitted)",
    )
    importer.add_argument(
        "--format", choices=formats.available(), help="file format (detected if omitted)"
    )
    importer.set_defaults(handler=import_csv)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
