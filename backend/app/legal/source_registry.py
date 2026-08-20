from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .models import OfficialSourceRef, SourceRole

SOURCE_REGISTRY_SCHEMA_VERSION = "1.0.0"


class LegalSourceRegistryError(RuntimeError):
    pass


class SourceTrustTier(str, Enum):
    AUTHORITATIVE_DATABASE = "AUTHORITATIVE_DATABASE"
    ENACTING_OR_ISSUING_BODY = "ENACTING_OR_ISSUING_BODY"
    CENTRAL_GOVERNMENT_PORTAL = "CENTRAL_GOVERNMENT_PORTAL"
    OFFICIAL_CROSS_CHECK = "OFFICIAL_CROSS_CHECK"


class RegisteredLegalSource(BaseModel):
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    organization: str = Field(min_length=1)
    hosts: list[str] = Field(min_length=1)
    trust_tier: SourceTrustTier
    allowed_roles: list[SourceRole] = Field(min_length=1)
    primary_normative_source_allowed: bool = False
    notes: str = Field(min_length=1)

    @field_validator("hosts")
    @classmethod
    def validate_hosts(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            host = value.strip().lower()
            if not host or host != value or "://" in host or "/" in host or "*" in host:
                raise ValueError("hosts must be exact lowercase hostnames without scheme, path, port or wildcard")
            if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for character in host):
                raise ValueError("hosts must contain ASCII hostname characters only")
            normalized.append(host)
        if len(set(normalized)) != len(normalized):
            raise ValueError("hosts must not contain duplicates")
        return normalized

    @field_validator("allowed_roles")
    @classmethod
    def validate_allowed_roles(cls, values: list[SourceRole]) -> list[SourceRole]:
        if len(set(values)) != len(values):
            raise ValueError("allowed_roles must not contain duplicates")
        return values

    @model_validator(mode="after")
    def validate_primary_policy(self) -> "RegisteredLegalSource":
        if SourceRole.PRIMARY in self.allowed_roles and not self.primary_normative_source_allowed:
            raise ValueError("PRIMARY role requires primary_normative_source_allowed=true")
        return self


class LegalSourceRegistry(BaseModel):
    registry_schema_version: str = SOURCE_REGISTRY_SCHEMA_VERSION
    verified_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    sources: list[RegisteredLegalSource] = Field(min_length=1)

    @field_validator("registry_schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != SOURCE_REGISTRY_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported legal source registry schema {value}; expected {SOURCE_REGISTRY_SCHEMA_VERSION}."
            )
        return value

    @model_validator(mode="after")
    def validate_unique_identity(self) -> "LegalSourceRegistry":
        source_ids: set[str] = set()
        hosts: set[str] = set()
        for source in self.sources:
            if source.source_id in source_ids:
                raise ValueError(f"Duplicate source_id: {source.source_id}")
            source_ids.add(source.source_id)
            for host in source.hosts:
                if host in hosts:
                    raise ValueError(f"Host is registered more than once: {host}")
                hosts.add(host)
        return self


def load_source_registry(path: Path) -> LegalSourceRegistry:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LegalSourceRegistryError(f"Unable to read legal source registry {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LegalSourceRegistryError(f"Malformed JSON in legal source registry {path}: {exc}") from exc
    try:
        return LegalSourceRegistry.model_validate(payload)
    except ValidationError as exc:
        raise LegalSourceRegistryError(f"Malformed legal source registry {path}: {exc}") from exc


def source_for_host(registry: LegalSourceRegistry, host: str) -> RegisteredLegalSource | None:
    normalized = host.lower()
    for source in registry.sources:
        if normalized in source.hosts:
            return source
    return None


def validate_official_source_ref(ref: OfficialSourceRef, registry: LegalSourceRegistry) -> RegisteredLegalSource:
    parsed = urlsplit(str(ref.url))
    host = (parsed.hostname or "").lower()
    source = source_for_host(registry, host)
    if source is None:
        raise LegalSourceRegistryError(f"Unregistered official legal source host: {host or '<missing>'}")
    if ref.role not in source.allowed_roles:
        raise LegalSourceRegistryError(
            f"Source {source.source_id} does not allow role {ref.role.value} for {ref.url}"
        )
    if ref.role == SourceRole.PRIMARY and not source.primary_normative_source_allowed:
        raise LegalSourceRegistryError(f"Source {source.source_id} is not approved for PRIMARY normative use")
    return source
