"""Small runtime guards shared by CLI code and frozen GUI builds."""


def stream_isatty(stream):
    """Return whether *stream* is interactive without assuming it exists.

    Windows GUI executables created by PyInstaller may set ``sys.stdin`` and
    ``sys.stdout`` to ``None``.  Treat that as a non-interactive session.
    """
    try:
        return bool(stream is not None and stream.isatty())
    except (AttributeError, OSError, ValueError):
        return False
