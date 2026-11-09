"""Check or upgrade the local archive; preserve a SQLite backup before changes."""
import argparse
import datetime
from pathlib import Path
import sqlite3
from server.core.database import DB_PATH, engine, init_db
from server.core.migrations import schema_version, LATEST_VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Report schema version without changing files')
    args = parser.parse_args()
    path = Path(DB_PATH)
    if args.check:
        if not path.exists():
            print('Database does not exist; startup will initialize it.')
            return
        with engine.connect() as connection:
            print(f'Schema version: {schema_version(connection)}; supported: {LATEST_VERSION}')
        return
    if path.exists():
        folder = Path(__file__).resolve().parent / '.venv' / 'backups'
        folder.mkdir(parents=True, exist_ok=True)
        backup = folder / f'quant-{datetime.datetime.now():%Y%m%d-%H%M%S-%f}.db'
        with sqlite3.connect(path) as source, sqlite3.connect(backup) as destination:
            source.backup(destination)
        print(f'Backup: {backup}')
    init_db()
    print(f'Schema ready: {LATEST_VERSION}')


if __name__ == '__main__':
    main()
