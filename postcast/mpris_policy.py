def seek_target(position, duration, offset):
    """Return an MPRIS seek target in seconds, clamped to the track."""
    target = max(0, int(position) + int(offset))
    return min(target, int(duration)) if duration else target
