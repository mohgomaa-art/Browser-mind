# BrowserMind API sidecar package — module entry point.
# Allows: python -m browsermind_core.api.sidecar  (via __init__ re-export)
# and:    python -m browsermind_core.api           (this file)

from browsermind_core.api.sidecar import main

if __name__ == "__main__":
    main()
