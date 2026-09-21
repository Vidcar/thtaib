"""Destructive lifecycle decisions fail closed on unavailable durable state."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from workbench_backend.errors import ManagerError
from workbench_backend.paths import WorkbenchPaths
from workbench_backend.inference.schemas import Deployment, DeploymentStatus, ManagementScope
from workbench_backend.inference.service import ModelManager


class LifecycleGuardFailureTests(unittest.TestCase):
    def test_direct_stop_cannot_bypass_unreadable_active_run_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = ModelManager(WorkbenchPaths(Path(tmp)))
            deployment = Deployment(id='guard-test',display_name='guard test',scope=ManagementScope.managed,
                status=DeploymentStatus.stopped,created_at='2026-09-21T00:00:00Z',updated_at='2026-09-21T00:00:00Z')
            manager.store.put_deployment(deployment)
            with patch('workbench_backend.inference.service.open_application_store',side_effect=OSError('unavailable')):
                with self.assertRaises(ManagerError) as caught:
                    manager.deployments.stop(deployment.id)
            self.assertEqual(caught.exception.code,'model_dependencies_unavailable')
            self.assertEqual(manager.store.get_deployment(deployment.id),deployment)


if __name__ == '__main__': unittest.main()
