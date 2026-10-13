"""Admin commands, e.g. `python -m app.cli create-user --email you@example.com`."""

import argparse
import getpass
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db import get_sessionmaker
from app.schemas.auth import RegisterRequest
from app.services import users


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

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
