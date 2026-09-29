import os

# Keep limits small and deterministic for tests; must be set before app import.
os.environ.setdefault("MAX_UPLOAD_MB", "1")
os.environ.setdefault("MAX_TOTAL_UPLOAD_MB", "2")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "1000")
os.environ.setdefault("ALLOWED_HOSTS", "testserver,127.0.0.1,localhost")
os.environ.setdefault("AUDIO_JOBS_PER_MINUTE", "1000")
os.environ.setdefault("AUDIO_DOWNLOAD_HOSTS", "nas.example.lan")
