"""Compatibility entry point for the versioned payment migrations."""


def initialize_schema():
    from app.migration_runner import apply_migrations

    return apply_migrations()
