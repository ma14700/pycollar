"""Compatibility alias for python run.py; application code lives in server/."""
from run import main

if __name__ == '__main__':
    raise SystemExit(main())
