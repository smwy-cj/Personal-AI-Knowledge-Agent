"""Secret-safe credential storage boundaries.

Credential values deliberately never appear in public status objects or error
messages. The production keyring dependency is loaded lazily so offline tests
can use deterministic fake backends without touching a user's credential store.
"""

from dataclasses import dataclass
import os
import warnings
from typing import Callable, Dict, Mapping, Optional, Protocol


KEYRING_SERVICE_NAME = "personal-ai-knowledge-agent"


class CredentialStoreError(RuntimeError):
    """A credential operation failed without exposing the credential value."""


class CredentialBackendUnavailable(CredentialStoreError):
    """No secure operating-system credential backend is available."""


@dataclass(frozen=True)
class CredentialStatus:
    provider_id: str
    configured: bool
    source: str
    backend_available: bool


class CredentialStore(Protocol):
    def get(self, provider_id: str) -> Optional[str]:
        ...

    def set(self, provider_id: str, credential: str) -> CredentialStatus:
        ...

    def status(self, provider_id: str) -> CredentialStatus:
        ...

    def delete(self, provider_id: str) -> bool:
        ...


class KeyringBackend(Protocol):
    priority: object

    def get_password(self, service: str, username: str) -> Optional[str]:
        ...

    def set_password(self, service: str, username: str, value: str) -> None:
        ...

    def delete_password(self, service: str, username: str) -> None:
        ...


class InMemoryCredentialStore:
    """Deterministic test store with the same public contract as keyring."""

    def __init__(self) -> None:
        self._credentials: Dict[str, str] = {}

    def get(self, provider_id: str) -> Optional[str]:
        return self._credentials.get(_provider_id(provider_id))

    def set(self, provider_id: str, credential: str) -> CredentialStatus:
        normalized = _provider_id(provider_id)
        value = _credential_value(credential)
        self._credentials[normalized] = value
        return self.status(normalized)

    def status(self, provider_id: str) -> CredentialStatus:
        normalized = _provider_id(provider_id)
        configured = normalized in self._credentials
        return CredentialStatus(
            provider_id=normalized,
            configured=configured,
            source="keyring" if configured else "none",
            backend_available=True,
        )

    def delete(self, provider_id: str) -> bool:
        normalized = _provider_id(provider_id)
        return self._credentials.pop(normalized, None) is not None


class KeyringCredentialStore:
    def __init__(self, backend: KeyringBackend) -> None:
        self._backend = backend

    @classmethod
    def from_system(cls) -> "KeyringCredentialStore":
        try:
            # Some legacy keyring backend loaders still use the pre-PEP 451
            # import hooks. Python emits ImportWarning for those hooks when a
            # test runner enables normally-hidden import warnings; the warning
            # is owned by the third-party loader and must not pollute JSON CLI
            # stderr. Keep the suppression limited to backend discovery.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ImportWarning)
                import keyring

                backend = keyring.get_keyring()
        except ImportError as exc:
            raise CredentialBackendUnavailable(
                "the operating-system credential backend is not installed"
            ) from exc
        return cls(backend)

    def get(self, provider_id: str) -> Optional[str]:
        normalized = _provider_id(provider_id)
        self._require_available()
        try:
            return self._backend.get_password(
                KEYRING_SERVICE_NAME, _username(normalized)
            )
        except Exception as exc:
            raise CredentialStoreError("could not read the provider credential") from exc

    def set(self, provider_id: str, credential: str) -> CredentialStatus:
        normalized = _provider_id(provider_id)
        value = _credential_value(credential)
        self._require_available()
        try:
            self._backend.set_password(
                KEYRING_SERVICE_NAME, _username(normalized), value
            )
        except Exception as exc:
            raise CredentialStoreError("could not store the provider credential") from exc
        return CredentialStatus(normalized, True, "keyring", True)

    def status(self, provider_id: str) -> CredentialStatus:
        normalized = _provider_id(provider_id)
        if not self._available():
            return CredentialStatus(normalized, False, "none", False)
        try:
            configured = (
                self._backend.get_password(
                    KEYRING_SERVICE_NAME, _username(normalized)
                )
                is not None
            )
        except Exception as exc:
            raise CredentialStoreError(
                "could not inspect the provider credential"
            ) from exc
        return CredentialStatus(
            normalized, configured, "keyring" if configured else "none", True
        )

    def delete(self, provider_id: str) -> bool:
        normalized = _provider_id(provider_id)
        self._require_available()
        username = _username(normalized)
        try:
            if self._backend.get_password(KEYRING_SERVICE_NAME, username) is None:
                return False
            self._backend.delete_password(KEYRING_SERVICE_NAME, username)
            return True
        except Exception as exc:
            raise CredentialStoreError("could not delete the provider credential") from exc

    def _require_available(self) -> None:
        if not self._available():
            raise CredentialBackendUnavailable(
                "a secure operating-system credential backend is unavailable"
            )

    def _available(self) -> bool:
        try:
            priority = self._backend.priority
            if callable(priority):
                priority = priority()
            return float(priority) > 0
        except (AttributeError, TypeError, ValueError):
            return False


def _provider_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CredentialStoreError("provider_id must be a non-empty identifier")
    normalized = value.strip()
    if not all(character.isalnum() or character in "._-" for character in normalized):
        raise CredentialStoreError("provider_id contains unsupported characters")
    return normalized


def _credential_value(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CredentialStoreError("credential must be non-empty")
    return value


def _username(provider_id: str) -> str:
    return "provider:%s" % provider_id


class CredentialResolver:
    """Resolve a provider credential from keyring, then an explicit env name."""

    def __init__(
        self,
        store: Optional[CredentialStore] = None,
        environ: Optional[Mapping[str, str]] = None,
        store_factory: Optional[Callable[[], CredentialStore]] = None,
    ) -> None:
        self._store = store
        self._environ = os.environ if environ is None else environ
        self._store_factory = store_factory or KeyringCredentialStore.from_system
        self._store_loaded = store is not None

    def resolve(
        self, provider_id: str, environment_name: Optional[str]
    ) -> Optional[str]:
        normalized = _provider_id(provider_id)
        store = self._load_store()
        if store is not None:
            try:
                credential = store.get(normalized)
            except CredentialBackendUnavailable:
                credential = None
            if credential is not None:
                return credential
        if environment_name:
            return self._environ.get(environment_name) or None
        return None

    def status(
        self, provider_id: str, environment_name: Optional[str]
    ) -> CredentialStatus:
        normalized = _provider_id(provider_id)
        store = self._load_store()
        backend_available = False
        if store is not None:
            keyring_status = store.status(normalized)
            backend_available = keyring_status.backend_available
            if keyring_status.configured:
                return keyring_status
        if environment_name and self._environ.get(environment_name):
            return CredentialStatus(normalized, True, "environment", backend_available)
        return CredentialStatus(normalized, False, "none", backend_available)

    def _load_store(self) -> Optional[CredentialStore]:
        if self._store_loaded:
            return self._store
        self._store_loaded = True
        try:
            self._store = self._store_factory()
        except CredentialBackendUnavailable:
            self._store = None
        return self._store
