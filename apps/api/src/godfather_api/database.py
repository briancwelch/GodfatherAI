"""Bounded synchronous PostgreSQL access, owned by the API application lifespan."""

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from godfather_api.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self.environment = settings.environment
        timeout = settings.database_timeout_seconds
        self.engine: Engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_timeout=timeout,
            hide_parameters=True,
            connect_args={
                "connect_timeout": timeout,
                "options": f"-c timezone=UTC -c statement_timeout={timeout * 1000}",
            },
        )
        self.sessions: sessionmaker[Session] = sessionmaker(
            self.engine, expire_on_commit=False, info={"test": settings.environment == "test"}
        )

    def ready(self) -> bool:
        """Require connectivity and the exact migration head, without schema mutation."""
        from godfather_api.migrations import migration_head

        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            revisions = set(connection.scalars(text("SELECT version_num FROM alembic_version")))
        return revisions == {migration_head()}

    def close(self) -> None:
        self.engine.dispose()
