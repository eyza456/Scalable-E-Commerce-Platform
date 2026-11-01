"""Compatibility entry point for the versioned user migrations."""


def initialize_schema():
    from app.migration_runner import apply_migrations

    return apply_migrations()
