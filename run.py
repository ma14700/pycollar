"""Compatibility entry point for the maintained Windows project launcher."""
from pathlib import Path
import os
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    if os.name != 'nt':
        raise SystemExit('Use python -m uvicorn server.main:app and npm run dev on this platform.')
    return subprocess.call(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                            '-File', str(root / 'scripts' / 'start.ps1'), *sys.argv[1:]], cwd=root)


if __name__ == '__main__':
    raise SystemExit(main())
