import os

# Keep limits small and deterministic for tests; must be set before app import.
os.environ.setdefault("MAX_UPLOAD_MB", "1")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "1000")
