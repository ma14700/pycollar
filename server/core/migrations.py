"""Versioned, additive SQLite migrations for existing local archives."""
from sqlalchemy import inspect, text

LATEST_VERSION = 1


def schema_version(connection):
    if 'schema_migrations' not in inspect(connection).get_table_names():
        return 0
    return connection.execute(text('SELECT COALESCE(MAX(version), 0) FROM schema_migrations')).scalar_one()


def upgrade_database(engine):
    with engine.begin() as connection:
        version = schema_version(connection)
        if version > LATEST_VERSION:
            raise RuntimeError('数据库版本高于当前程序，请升级程序后再启动')
        if version == LATEST_VERSION:
            return version
        names = {column['name'] for column in inspect(connection).get_columns('backtest_records')}
        # Fixed SQL statements only; identifiers never come from a request.
        if 'strategy_name' not in names:
            connection.execute(text("ALTER TABLE backtest_records ADD COLUMN strategy_name VARCHAR DEFAULT 'TrendFollowingStrategy'"))
        if 'detail_data' not in names:
            connection.execute(text('ALTER TABLE backtest_records ADD COLUMN detail_data JSON'))
        connection.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)'))
        connection.execute(text('INSERT INTO schema_migrations (version) VALUES (1)'))
        return LATEST_VERSION
