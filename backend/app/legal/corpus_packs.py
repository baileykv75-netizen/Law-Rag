from __future__ import annotations

import json
from enum import Enum
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .models import LegalManifest

CORPUS_PACK_SCHEMA_VERSION = "1.0.0"


class CorpusPackError(RuntimeError):
    pass


class CorpusPackStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"


class CorpusPackManifest(BaseModel):
    pack_schema_version: str = CORPUS_PACK_SCHEMA_VERSION
    pack_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    pack_version: str = Field(pattern=r"^[0-9][0-9A-Za-z._-]{0,63}$")
    display_name: str = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)
    description: str = Field(min_length=1)
    domain_tags: list[str] = Field(min_length=1)
    status: CorpusPackStatus = CorpusPackStatus.DRAFT
    authority_manifest_paths: list[str] = Field(default_factory=list)

    @field_validator("pack_schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != CORPUS_PACK_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported corpus pack schema {value}; expected {CORPUS_PACK_SCHEMA_VERSION}."
            )
        return value

    @field_validator("domain_tags")
    @classmethod
    def validate_domain_tags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            tag = value.strip()
            if not tag or not tag[0].isalnum() or any(
                not (character.islower() or character.isdigit() or character in ".-_")
                for character in tag
            ):
                raise ValueError(
                    "domain_tags must be lowercase extensible slugs containing only a-z, 0-9, '.', '_' or '-'."
                )
            normalized.append(tag)
        if len(set(normalized)) != len(normalized):
            raise ValueError("domain_tags must not contain duplicates.")
        return normalized

    @field_validator("authority_manifest_paths")
    @classmethod
    def validate_manifest_reference_syntax(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value or value.strip() != value or "\\" in value:
                raise ValueError("authority_manifest_paths must use non-empty corpus-root-relative POSIX paths.")
            path = PurePosixPath(value)
            if path.is_absolute() or ".." in path.parts or "." in path.parts:
                raise ValueError("authority_manifest_paths may not be absolute or contain traversal segments.")
        if len(set(values)) != len(values):
            raise ValueError("authority_manifest_paths must not contain duplicate paths.")
        return values

    @model_validator(mode="after")
    def validate_ready_membership(self) -> "CorpusPackManifest":
        if self.status == CorpusPackStatus.READY and not self.authority_manifest_paths:
            raise ValueError("READY corpus packs must reference at least one authority manifest.")
        return self


class CorpusPackMember(BaseModel):
    authority_id: str
    version_id: str
    authority_manifest_path: str


class LoadedCorpusPack(BaseModel):
    manifest: CorpusPackManifest
    pack_path: str
    members: list[CorpusPackMember]


def _inside_root(candidate: Path, root: Path, *, label: str) -> Path:
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise CorpusPackError(f"{label} escapes corpus root: {candidate}") from exc
    return resolved_candidate


def _read_json(path: Path, *, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CorpusPackError(f"Unable to read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CorpusPackError(f"Malformed JSON in {label} {path}: {exc}") from exc


def _load_legal_manifest(path: Path) -> LegalManifest:
    payload = _read_json(path, label="authority manifest")
    try:
        return LegalManifest.model_validate(payload)
    except ValidationError as exc:
        raise CorpusPackError(f"Malformed authority manifest {path}: {exc}") from exc


def load_corpus_pack(pack_path: Path, corpus_root: Path) -> LoadedCorpusPack:
    root = corpus_root.resolve()
    resolved_pack_path = _inside_root(pack_path, root, label="Corpus pack manifest")
    payload = _read_json(resolved_pack_path, label="corpus pack manifest")
    try:
        manifest = CorpusPackManifest.model_validate(payload)
    except ValidationError as exc:
        raise CorpusPackError(f"Malformed corpus pack manifest {resolved_pack_path}: {exc}") from exc

    if resolved_pack_path.name != "pack.json" or resolved_pack_path.parent.name != manifest.pack_id:
        raise CorpusPackError(
            "Corpus pack location must be legal_data/packs/<pack_id>/pack.json and match pack_id."
        )

    members: list[CorpusPackMember] = []
    seen_identities: set[tuple[str, str]] = set()
    for configured_path in manifest.authority_manifest_paths:
        posix_path = PurePosixPath(configured_path)
        authority_path = root.joinpath(*posix_path.parts)
        authority_path = _inside_root(authority_path, root, label="Authority manifest")
        legal_manifest = _load_legal_manifest(authority_path)
        for record in legal_manifest.records:
            identity = (record.authority.authority_id, record.version_id)
            if identity in seen_identities:
                raise CorpusPackError(
                    f"Corpus pack {manifest.pack_id} contains duplicate authority/version identity "
                    f"{identity[0]}:{identity[1]}."
                )
            seen_identities.add(identity)
            members.append(
                CorpusPackMember(
                    authority_id=identity[0],
                    version_id=identity[1],
                    authority_manifest_path=configured_path,
                )
            )

    return LoadedCorpusPack(
        manifest=manifest,
        pack_path=resolved_pack_path.relative_to(root).as_posix(),
        members=members,
    )


def discover_corpus_packs(corpus_root: Path) -> list[LoadedCorpusPack]:
    root = corpus_root.resolve()
    packs_root = root / "packs"
    if not packs_root.exists():
        return []
    if not packs_root.is_dir():
        raise CorpusPackError(f"Corpus packs path is not a directory: {packs_root}")

    results: list[LoadedCorpusPack] = []
    seen_pack_ids: set[str] = set()
    for pack_path in sorted(packs_root.glob("*/pack.json"), key=lambda item: item.as_posix()):
        loaded = load_corpus_pack(pack_path, root)
        pack_id = loaded.manifest.pack_id
        if pack_id in seen_pack_ids:
            raise CorpusPackError(f"Duplicate corpus pack id discovered: {pack_id}")
        seen_pack_ids.add(pack_id)
        results.append(loaded)
    return results
