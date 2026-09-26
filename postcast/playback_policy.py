def rate_requires_seek(rate):
    """Whether a playback rate needs GStreamer's seek-based rate change."""
    return abs(float(rate) - 1.0) >= 0.001
