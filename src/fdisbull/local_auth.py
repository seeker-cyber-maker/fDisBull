"""Short-lived credentials for optional local TCP endpoints."""

import hmac
import os
from pathlib import Path
import secrets
import tempfile


class LocalCredential:
    def __init__(self, prefix):
        self._directory = tempfile.TemporaryDirectory(prefix=prefix)
        self.path = Path(self._directory.name) / 'token'
        self._token = secrets.token_hex(32)
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='ascii') as output:
                output.write(self._token + '\n')
        except BaseException:
            self.close()
            raise

    def check(self, value):
        return isinstance(value, str) and hmac.compare_digest(self._token, value)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self._directory.cleanup()
