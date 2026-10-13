"""Every migration must apply, roll back and re-apply, and match the ORM models."""

from alembic import command


def test_migrations_downgrade_and_upgrade_cleanly(engine, alembic_config):
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


def test_models_match_migrations(engine, alembic_config):
    command.check(alembic_config)
