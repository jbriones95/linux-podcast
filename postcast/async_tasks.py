import threading
from concurrent.futures import ThreadPoolExecutor


class AsyncCoordinator:
    """Run keyed work off-thread and discard stale results."""

    def __init__(self, max_workers=2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="postcast-query")
        self._lock = threading.Lock()
        self._generations = {}
        self._futures = {}
        self._closed = False

    def submit(self, key, work, callback, dispatch):
        with self._lock:
            if self._closed:
                return None
            generation = self._generations.get(key, 0) + 1
            self._generations[key] = generation
            previous = self._futures.get(key)
            if previous is not None:
                previous.cancel()
            future = self._executor.submit(work)
            self._futures[key] = future

        def completed(done):
            try:
                result = done.result()
            except Exception as exc:
                result = exc

            def deliver():
                with self._lock:
                    current = (
                        not self._closed
                        and self._generations.get(key) == generation
                        and self._futures.get(key) is future
                    )
                if current:
                    callback(result)
                return False

            dispatch(deliver)

        future.add_done_callback(completed)
        return generation

    def cancel(self, key):
        with self._lock:
            self._generations[key] = self._generations.get(key, 0) + 1
            future = self._futures.pop(key, None)
            if future is not None:
                future.cancel()

    def close(self):
        with self._lock:
            self._closed = True
            for future in self._futures.values():
                future.cancel()
            self._futures.clear()
        self._executor.shutdown(wait=True, cancel_futures=True)
