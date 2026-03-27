"""Startup sanity check for CI.

This script fails fast if importing the Flask app raises an exception
(for example duplicate route endpoint registration).
"""

from importlib import import_module
from pathlib import Path
import sys


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))
    module = import_module("app")
    app = getattr(module, "app", None)
    if app is None:
        raise RuntimeError("Imported module `app` but no Flask app object named `app` was found.")
    print(f"Startup sanity check passed. Loaded Flask app: {app.import_name}")


if __name__ == "__main__":
    main()
