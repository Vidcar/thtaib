"""OS credential vault. Backups retain bindings, never the values."""
import hashlib
import keyring
from workbench_backend.errors import HarnessError


class CredentialVault:
    def __init__(self, root):
        self.service = "LocalAIWorkbench.connections." + hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]

    def get(self, reference):
        if not reference:
            return None
        try:
            return keyring.get_password(self.service, reference)
        except Exception:
            raise HarnessError("The Windows credential store is unavailable.", code="credential_store_unavailable", status_code=503) from None

    def put(self, reference, secret):
        try:
            keyring.set_password(self.service, reference, secret)
        except Exception:
            raise HarnessError("The credential could not be saved in the Windows credential store.", code="credential_store_unavailable", status_code=503) from None

    def remove(self, reference):
        if self.get(reference) is not None:
            try:
                keyring.delete_password(self.service, reference)
            except Exception:
                raise HarnessError("The local credential could not be removed.", code="credential_store_unavailable", status_code=503) from None
