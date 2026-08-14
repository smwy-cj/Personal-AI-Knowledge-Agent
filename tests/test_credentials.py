import unittest

from personal_ai_agent.credentials import (
    CredentialBackendUnavailable,
    CredentialStoreError,
    InMemoryCredentialStore,
    KeyringCredentialStore,
)


class InMemoryCredentialStoreTests(unittest.TestCase):
    def test_set_status_overwrite_and_delete_never_expose_value(self):
        store = InMemoryCredentialStore()

        created = store.set("primary-model", "first-private-value")
        self.assertEqual("primary-model", created.provider_id)
        self.assertTrue(created.configured)
        self.assertEqual("keyring", created.source)
        self.assertTrue(created.backend_available)
        self.assertNotIn("first-private-value", repr(created))

        store.set("primary-model", "second-private-value")
        self.assertEqual("second-private-value", store.get("primary-model"))
        self.assertNotIn("second-private-value", repr(store.status("primary-model")))

        self.assertTrue(store.delete("primary-model"))
        self.assertFalse(store.delete("primary-model"))
        missing = store.status("primary-model")
        self.assertFalse(missing.configured)
        self.assertEqual("none", missing.source)

    def test_rejects_invalid_provider_and_blank_credential_without_echo(self):
        store = InMemoryCredentialStore()
        marker = "must-not-appear"

        for provider_id in ("", "with space", "provider/name"):
            with self.subTest(provider_id=provider_id), self.assertRaises(
                CredentialStoreError
            ):
                store.set(provider_id, marker)

        with self.assertRaises(CredentialStoreError) as raised:
            store.set("provider", "   ")
        self.assertNotIn(marker, str(raised.exception))

    def test_accepts_non_blank_unicode_credential_verbatim(self):
        store = InMemoryCredentialStore()
        value = "密钥-🔐-value"
        store.set("provider_1", value)
        self.assertEqual(value, store.get("provider_1"))


class FakeKeyringBackend:
    priority = 1

    def __init__(self):
        self.values = {}
        self.fail_set = False

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, value):
        if self.fail_set:
            raise RuntimeError("backend rejected secret")
        self.values[(service, username)] = value

    def delete_password(self, service, username):
        key = (service, username)
        if key not in self.values:
            raise KeyError(username)
        del self.values[key]


class KeyringCredentialStoreTests(unittest.TestCase):
    def test_uses_stable_namespace_and_safe_status(self):
        backend = FakeKeyringBackend()
        store = KeyringCredentialStore(backend)

        status = store.set("Provider_A", "private-value")

        self.assertEqual(
            "private-value",
            backend.values[("personal-ai-knowledge-agent", "provider:Provider_A")],
        )
        self.assertEqual("keyring", status.source)
        self.assertNotIn("private-value", repr(status))
        self.assertEqual("private-value", store.get("Provider_A"))

    def test_backend_unavailable_is_explicit(self):
        backend = FakeKeyringBackend()
        backend.priority = 0
        store = KeyringCredentialStore(backend)

        status = store.status("provider")
        self.assertFalse(status.backend_available)
        self.assertFalse(status.configured)

        with self.assertRaises(CredentialBackendUnavailable):
            store.set("provider", "private-value")

    def test_failed_overwrite_preserves_old_value_and_hides_new_value(self):
        backend = FakeKeyringBackend()
        store = KeyringCredentialStore(backend)
        store.set("provider", "old-private-value")
        backend.fail_set = True

        with self.assertRaises(CredentialStoreError) as raised:
            store.set("provider", "new-private-value")

        self.assertEqual("old-private-value", store.get("provider"))
        self.assertNotIn("new-private-value", str(raised.exception))

    def test_delete_is_idempotent(self):
        backend = FakeKeyringBackend()
        store = KeyringCredentialStore(backend)

        self.assertFalse(store.delete("provider"))
        store.set("provider", "private-value")
        self.assertTrue(store.delete("provider"))
        self.assertFalse(store.delete("provider"))


if __name__ == "__main__":
    unittest.main()
