import functools
import logging
import time


logger = logging.getLogger("postcast.performance")


def timed(operation):
    """Log debug timing for an operation without changing its return value."""
    def decorator(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            if not logger.isEnabledFor(logging.DEBUG):
                return func(*args, **kwargs)
            started = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - started) * 1000
            count = len(result) if isinstance(result, (list, tuple)) else None
            suffix = f" rows={count}" if count is not None else ""
            logger.debug("%s duration_ms=%.2f%s", operation, elapsed_ms, suffix)
            return result
        return wrapped
    return decorator
