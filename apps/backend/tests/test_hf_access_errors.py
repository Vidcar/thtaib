"""Metadata failures remain actionable without exposing credentials."""
import unittest
from unittest.mock import patch
import httpx
from huggingface_hub.errors import GatedRepoError, HfHubHTTPError, OfflineModeIsEnabled
from workbench_backend.errors import ManagerError
from workbench_backend.inference.hf_fetch import HuggingFaceFetcher


class HubAccessTests(unittest.TestCase):
    def test_lazy_search_and_inspect_classify_access_failure(self):
        failures = [(OfflineModeIsEnabled('offline'), 'hf_offline'),
                    (httpx.ConnectError('offline'), 'hf_offline'),
                    (GatedRepoError('gated', response=httpx.Response(403, request=httpx.Request('GET','https://huggingface.co'))), 'hf_gated')]
        for status, code in [(401,'hf_authentication'), (403,'hf_inaccessible'), (404,'hf_inaccessible'), (503,'hf_service')]:
            failures.append((HfHubHTTPError('sensitive-token-not-for-output', response=httpx.Response(status, request=httpx.Request('GET','https://huggingface.co'))), code))
        for error, code in failures:
            with self.subTest(code=code):
                def lazy():
                    raise error
                    yield None
                with patch('workbench_backend.inference.hf_fetch.HfApi') as api:
                    api.return_value.list_models.return_value = lazy()
                    api.return_value.model_info.side_effect = error
                    for call in (lambda: HuggingFaceFetcher().search('test'), lambda: HuggingFaceFetcher().inspect(repo_id='org/model')):
                        with self.assertRaises(ManagerError) as caught:
                            call()
                        self.assertEqual(caught.exception.code, code)
                        self.assertNotIn('sensitive-token', caught.exception.message)


if __name__ == '__main__': unittest.main()
