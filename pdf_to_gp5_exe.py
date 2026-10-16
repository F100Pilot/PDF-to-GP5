"""Entry point of the Windows program built by PyInstaller (see pdf-to-gp5.spec). Not used when the
app runs from the source (start.bat runs ``python -m app``)."""

import multiprocessing

if __name__ == "__main__":
    # The conversions run in a child process: in the program, that child is this same .exe, and
    # freeze_support() makes it run the child's work instead of starting the app again.
    multiprocessing.freeze_support()
    from app.launcher import main

    raise SystemExit(main())
