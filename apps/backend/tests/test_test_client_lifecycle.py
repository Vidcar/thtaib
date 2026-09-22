"""Polling fixtures retain one request loop and release it deterministically."""
import asyncio
from contextlib import asynccontextmanager
import unittest

from fastapi import FastAPI

from tests.support import close_workbench_sqlite, workbench_client


class TestClientLifecycleTests(unittest.TestCase):
    def make_app(self):
        loops, lifecycle = [], []

        @asynccontextmanager
        async def lifespan(app):
            lifecycle.append("start")
            yield
            lifecycle.append("stop")

        app = FastAPI(lifespan=lifespan)
        app.state.local_trust_token = "fixture-token"

        @app.get("/poll")
        async def poll():
            loops.append(asyncio.get_running_loop())
            return {"ok": True}

        return app, loops, lifecycle

    def test_polling_reuses_request_loop_and_app_cleanup_closes_every_client(self):
        app, loops, lifecycle = self.make_app()
        clients = [workbench_client(app), workbench_client(app, token="")]
        try:
            for client in clients:
                for _ in range(5):
                    self.assertEqual(client.get("/poll").json(), {"ok": True})
            self.assertEqual(len({id(loop) for loop in loops}), 2,
                             "Each request created another Windows self-pipe socket pair")
            self.assertEqual(lifecycle, [], "Unscoped fixture requests must not start the queue coordinator")
            # Some fixtures have only the application available at teardown.
            close_workbench_sqlite(app)
            self.assertTrue(all(loop.is_closed() for loop in loops))
            for client in clients:
                self.assertTrue(client.is_closed)
                with self.assertRaises(RuntimeError):
                    client.get("/poll")
        finally:
            for client in clients:
                client.close()
            close_workbench_sqlite(app)

    def test_explicit_context_retains_native_lifespan_and_closes_client(self):
        app, loops, lifecycle = self.make_app()
        client = workbench_client(app)
        try:
            with client:
                self.assertEqual(lifecycle, ["start"])
                client.get("/poll")
                client.get("/poll")
                self.assertIs(loops[0], loops[1])
            self.assertEqual(lifecycle, ["start", "stop"])
            self.assertTrue(loops[0].is_closed())
            with self.assertRaises(RuntimeError):
                client.get("/poll")
        finally:
            client.close()
            close_workbench_sqlite(app)
