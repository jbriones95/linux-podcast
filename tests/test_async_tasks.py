import threading
import unittest

from postcast.async_tasks import AsyncCoordinator


class AsyncCoordinatorTests(unittest.TestCase):
    def test_dispatches_result(self):
        coordinator = AsyncCoordinator()
        received = []
        coordinator.submit("search", lambda: 42, received.append, lambda fn: fn())
        coordinator.close()
        self.assertEqual(received, [42])

    def test_discards_stale_result(self):
        coordinator = AsyncCoordinator()
        first_started = threading.Event()
        release_first = threading.Event()
        pending = []
        received = []

        def first():
            first_started.set()
            release_first.wait(1)
            return "old"

        coordinator.submit("search", first, received.append, pending.append)
        self.assertTrue(first_started.wait(1))
        coordinator.submit("search", lambda: "new", received.append, pending.append)
        release_first.set()
        coordinator._futures["search"].result(timeout=1)
        for deliver in list(pending):
            deliver()
        coordinator.close()
        self.assertEqual(received, ["new"])


if __name__ == "__main__":
    unittest.main()
