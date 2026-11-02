from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, JSON, String, Text, UniqueConstraint, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    # UTC naive timestamps are stored consistently across PostgreSQL and test SQLite.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Target(Base):
    __tablename__ = "targets"
    __table_args__ = (UniqueConstraint("host", "container"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    host: Mapped[str] = mapped_column(String(253))
    container: Mapped[str] = mapped_column(String(255), default="")
    display_name: Mapped[str] = mapped_column(Text, default="")
    projects: Mapped[list] = mapped_column(JSON, default=list)
    owners: Mapped[list] = mapped_column(JSON, default=list)
    declared_projects: Mapped[list] = mapped_column(JSON, default=list)
    declared_owners: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    rabbitmq: Mapped[dict] = mapped_column(JSON, default=dict)
    rabbitmq_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    server_config: Mapped[dict] = mapped_column(JSON, default=dict)
    disk_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    configured_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    reason: Mapped[str] = mapped_column(Text, default="Chưa kiểm tra")
    failures: Mapped[int] = mapped_column(Integer, default=0)
    successes: Mapped[int] = mapped_column(Integer, default=0)
    # A failing Docker query is distinct from a stopped container.
    query_failures: Mapped[int] = mapped_column(Integer, default=0)
    query_successes: Mapped[int] = mapped_column(Integer, default=0)


class RabbitMQConnection(Base):
    __tablename__ = "rabbitmq_connections"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    config: Mapped[dict] = mapped_column(JSON)


class TelegramUser(Base):
    __tablename__ = "telegram_users"
    # Case-insensitive key matching the names selected in the monitoring Sheet.
    owner: Mapped[str] = mapped_column(String(200), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(16))
    username: Mapped[str] = mapped_column(String(33), default="")


class Sample(Base):
    __tablename__ = "samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)


class ComposeService(Base):
    __tablename__ = "compose_services"
    __table_args__ = (UniqueConstraint("target_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    reason: Mapped[str] = mapped_column(Text, default="")
    containers: Mapped[list] = mapped_column(JSON, default=list)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Health(Base):
    __tablename__ = "component_health"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    error: Mapped[str] = mapped_column(Text, default="")


class AvailabilityInterval(Base):
    __tablename__ = "availability_intervals"
    __table_args__ = (Index("ix_availability_target_start", "target_id", "started_at"), Index("ix_availability_closed", "ended_at"))
    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")


class AvailabilityCursor(Base):
    __tablename__ = "availability_cursors"
    target_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    recorded_since: Mapped[datetime] = mapped_column(DateTime)
    interval_id: Mapped[int] = mapped_column(Integer)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AvailabilityDaily(Base):
    __tablename__ = "availability_daily"
    target_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    up_seconds: Mapped[float] = mapped_column(Float, default=0)
    down_seconds: Mapped[float] = mapped_column(Float, default=0)
    unknown_seconds: Mapped[float] = mapped_column(Float, default=0)
    disabled_seconds: Mapped[float] = mapped_column(Float, default=0)
    downtime_count: Mapped[int] = mapped_column(Integer, default=0)


class Incident(Base):
    __tablename__ = "incidents"
    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    detail: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_enqueued_at: Mapped[datetime] = mapped_column(DateTime)


class Outbox(Base):
    __tablename__ = "notification_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_key: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_error: Mapped[str] = mapped_column(Text, default="")


def connect(url):
    options = {"connect_timeout": 5} if url.startswith("postgresql") else {}
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True, connect_args=options)
    return engine, sessionmaker(engine, expire_on_commit=False)


def initialize(engine):
    """Create new tables and apply additive upgrades without replacing existing data."""
    Base.metadata.create_all(engine)
    telegram_columns = {c["name"] for c in inspect(engine).get_columns("telegram_users")}
    if "username" not in telegram_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE telegram_users ADD COLUMN username VARCHAR(33) NOT NULL DEFAULT ''"))
    columns = {c["name"] for c in inspect(engine).get_columns("targets")}
    for field in ("server_config", "disk_metrics"):
        if field not in columns:
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE targets ADD COLUMN {field} JSON NOT NULL DEFAULT '{{}}'"))
    if "rabbitmq" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE targets ADD COLUMN rabbitmq JSON NOT NULL DEFAULT '{}'"))
    if "rabbitmq_metrics" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE targets ADD COLUMN rabbitmq_metrics JSON NOT NULL DEFAULT '{}'"))
    if "note" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE targets ADD COLUMN note TEXT NOT NULL DEFAULT ''"))
    if "display_name" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE targets ADD COLUMN display_name TEXT NOT NULL DEFAULT ''"))
    if "archived" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE targets ADD COLUMN archived BOOLEAN NOT NULL DEFAULT FALSE"))


def heartbeat(session, name, error="", success=True):
    item = session.get(Health, name)
    if item is None:
        item = Health(name=name)
        session.add(item)
    item.last_attempt_at = now()
    item.error = error
    if success:
        item.last_ok_at = now()
