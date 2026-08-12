"""Secret-free application configuration with strict path validation."""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, FrozenSet, List, Optional, Union
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    pass


FORBIDDEN_KEY_PARTS = {"api_key", "apikey", "secret", "token", "password"}
ALLOWED_KEYS = {
    "vault_path",
    "data_directory",
    "managed_memory_directory",
    "model_providers",
    "embedding_providers",
    "observability_retention_days",
}


@dataclass(frozen=True)
class ModelProviderConfig:
    provider_id: str
    base_url: str
    model: str
    credential_env: Optional[str]
    capabilities: FrozenSet[str]
    max_context_tokens: int
    cost_level: str
    max_privacy_level: str
    priority: int = 100
    requests_per_minute: int = 60
    max_rate_limit_wait_seconds: float = 30.0
    input_cost_per_million_tokens_usd: float = 0.0
    output_cost_per_million_tokens_usd: float = 0.0


@dataclass(frozen=True)
class EmbeddingProviderConfig:
    provider_id: str
    base_url: str
    model: str
    dimension: int
    credential_env: Optional[str]
    batch_size: int = 32
    requests_per_minute: int = 60
    max_rate_limit_wait_seconds: float = 30.0


@dataclass(frozen=True)
class ApplicationConfig:
    vault_path: Path
    data_directory: Path
    managed_memory_directory: str = "Agent/Memory"
    model_providers: List[ModelProviderConfig] = field(default_factory=list)
    embedding_providers: List[EmbeddingProviderConfig] = field(default_factory=list)
    observability_retention_days: int = 90

    @classmethod
    def load(cls, config_path: Union[str, Path]) -> "ApplicationConfig":
        path = Path(config_path).resolve()
        if not path.is_file():
            raise ConfigurationError("configuration file does not exist")
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigurationError("configuration must be valid UTF-8 JSON") from exc
        if not isinstance(document, dict):
            raise ConfigurationError("configuration root must be an object")
        _reject_secret_keys(document)
        unknown = set(document) - ALLOWED_KEYS
        if unknown:
            raise ConfigurationError("unknown configuration keys: %s" % sorted(unknown))
        missing = {"vault_path", "data_directory"} - set(document)
        if missing:
            raise ConfigurationError("missing configuration keys: %s" % sorted(missing))

        vault = _resolve_path(path.parent, document["vault_path"])
        data = _resolve_path(path.parent, document["data_directory"])
        if not vault.is_dir():
            raise ConfigurationError("vault_path must be an existing directory")
        if _is_within(data, vault) or _is_within(vault, data):
            raise ConfigurationError("data_directory and vault_path must be separate")
        managed = _managed_directory(document.get("managed_memory_directory", "Agent/Memory"))
        models = _model_providers(document.get("model_providers", []))
        embeddings = _embedding_providers(document.get("embedding_providers", []))
        retention_days = _positive_integer(
            document.get("observability_retention_days", 90),
            "observability_retention_days",
        )
        provider_ids = [item.provider_id for item in models + embeddings]
        if len(provider_ids) != len(set(provider_ids)):
            raise ConfigurationError("provider_id values must be unique")
        return cls(vault, data, managed, models, embeddings, retention_days)

    def as_public_dict(self) -> Dict[str, object]:
        return {
            "vault_path": str(self.vault_path),
            "data_directory": str(self.data_directory),
            "managed_memory_directory": self.managed_memory_directory,
            "model_provider_ids": [item.provider_id for item in self.model_providers],
            "embedding_provider_ids": [item.provider_id for item in self.embedding_providers],
            "observability_retention_days": self.observability_retention_days,
        }


def _reject_secret_keys(value: Any, prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).casefold().replace("-", "_")
            components = normalized.split("_")
            if (
                normalized in FORBIDDEN_KEY_PARTS
                or "secret" in components
                or "token" in components
                or "password" in components
                or ("api" in components and "key" in components)
            ):
                raise ConfigurationError("configuration must not contain secret field: %s%s" % (prefix, key))
            _reject_secret_keys(nested, "%s%s." % (prefix, key))
    elif isinstance(value, list):
        for nested in value:
            _reject_secret_keys(nested, prefix)


def _resolve_path(base: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError("configured paths must be non-empty strings")
    candidate = Path(value.strip())
    return (candidate if candidate.is_absolute() else base / candidate).resolve()


def _managed_directory(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError("managed_memory_directory must be non-empty")
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ConfigurationError("managed_memory_directory must be a safe relative path")
    if ".obsidian" in {part.casefold() for part in path.parts}:
        raise ConfigurationError("managed_memory_directory cannot be inside .obsidian")
    return path.as_posix()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _model_providers(value: Any) -> List[ModelProviderConfig]:
    allowed = {
        "provider_id", "base_url", "model", "credential_env", "capabilities",
        "max_context_tokens", "cost_level", "max_privacy_level", "priority",
        "requests_per_minute", "max_rate_limit_wait_seconds",
        "input_cost_per_million_tokens_usd",
        "output_cost_per_million_tokens_usd",
    }
    items = _provider_objects(value, "model_providers", allowed)
    output = []
    for item in items:
        capabilities = item.get("capabilities", ["structured_output"])
        if not isinstance(capabilities, list) or not capabilities:
            raise ConfigurationError("model provider capabilities must be a non-empty list")
        output.append(
            ModelProviderConfig(
                provider_id=_identifier(item.get("provider_id"), "provider_id"),
                base_url=_base_url(item.get("base_url"), item.get("credential_env")),
                model=_non_empty(item.get("model"), "model"),
                credential_env=_environment_name(item.get("credential_env")),
                capabilities=frozenset(
                    _identifier(capability, "capability") for capability in capabilities
                ),
                max_context_tokens=_positive_integer(
                    item.get("max_context_tokens"), "max_context_tokens"
                ),
                cost_level=_choice(item.get("cost_level", "medium"), "cost_level", {"low", "medium", "high"}),
                max_privacy_level=_choice(
                    item.get("max_privacy_level", "personal"),
                    "max_privacy_level",
                    {"public", "personal", "sensitive"},
                ),
                priority=_non_negative_integer(item.get("priority", 100), "priority"),
                requests_per_minute=_positive_integer(
                    item.get("requests_per_minute", 60), "requests_per_minute"
                ),
                max_rate_limit_wait_seconds=_non_negative_number(
                    item.get("max_rate_limit_wait_seconds", 30.0),
                    "max_rate_limit_wait_seconds",
                ),
                input_cost_per_million_tokens_usd=_non_negative_number(
                    item.get("input_cost_per_million_tokens_usd", 0.0),
                    "input_cost_per_million_tokens_usd",
                ),
                output_cost_per_million_tokens_usd=_non_negative_number(
                    item.get("output_cost_per_million_tokens_usd", 0.0),
                    "output_cost_per_million_tokens_usd",
                ),
            )
        )
    return output


def _embedding_providers(value: Any) -> List[EmbeddingProviderConfig]:
    allowed = {
        "provider_id", "base_url", "model", "dimension", "credential_env", "batch_size",
        "requests_per_minute", "max_rate_limit_wait_seconds",
    }
    items = _provider_objects(value, "embedding_providers", allowed)
    return [
        EmbeddingProviderConfig(
            provider_id=_identifier(item.get("provider_id"), "provider_id"),
            base_url=_base_url(item.get("base_url"), item.get("credential_env")),
            model=_non_empty(item.get("model"), "model"),
            dimension=_positive_integer(item.get("dimension"), "dimension"),
            credential_env=_environment_name(item.get("credential_env")),
            batch_size=_positive_integer(item.get("batch_size", 32), "batch_size"),
            requests_per_minute=_positive_integer(
                item.get("requests_per_minute", 60), "requests_per_minute"
            ),
            max_rate_limit_wait_seconds=_non_negative_number(
                item.get("max_rate_limit_wait_seconds", 30.0),
                "max_rate_limit_wait_seconds",
            ),
        )
        for item in items
    ]


def _provider_objects(value: Any, name: str, allowed: set) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        raise ConfigurationError("%s must be a list" % name)
    output = []
    for item in value:
        if not isinstance(item, dict):
            raise ConfigurationError("%s entries must be objects" % name)
        unknown = set(item) - allowed
        if unknown:
            raise ConfigurationError("unknown %s keys: %s" % (name, sorted(unknown)))
        output.append(item)
    return output


def _base_url(value: Any, credential_env: Any) -> str:
    text = _non_empty(value, "base_url").rstrip("/")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError("base_url must be an HTTP(S) origin or path")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ConfigurationError("base_url cannot contain credentials, query or fragment")
    if credential_env is not None and parsed.scheme != "https":
        raise ConfigurationError("providers using credentials require HTTPS")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ConfigurationError("plain HTTP providers must use a loopback host")
    return text


def _environment_name(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = _identifier(value, "credential_env")
    if not text.replace("_", "").isalnum() or not (text[0].isalpha() or text[0] == "_"):
        raise ConfigurationError("credential_env must be an environment variable name")
    return text


def _identifier(value: Any, name: str) -> str:
    text = _non_empty(value, name)
    if not all(character.isalnum() or character in "._-" for character in text):
        raise ConfigurationError("%s contains unsupported characters" % name)
    return text


def _non_empty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError("%s must be a non-empty string" % name)
    return value.strip()


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError("%s must be a positive integer" % name)
    return value


def _non_negative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError("%s must be a non-negative integer" % name)
    return value


def _non_negative_number(value: Any, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ConfigurationError("%s must be a non-negative number" % name)
    return float(value)


def _choice(value: Any, name: str, choices: set) -> str:
    text = _non_empty(value, name).casefold()
    if text not in choices:
        raise ConfigurationError("%s must be one of %s" % (name, sorted(choices)))
    return text
