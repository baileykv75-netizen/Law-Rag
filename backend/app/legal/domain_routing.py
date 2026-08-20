from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from ..audit_plan_models import AuditPlanIssue, ContractType
from .corpus_packs import CorpusPackError, CorpusPackStatus, LoadedCorpusPack, discover_corpus_packs

DOMAIN_ROUTER_VERSION = "stage15.4-1.0.0"
DEFAULT_CORPUS_ROOT = Path(__file__).resolve().parents[3] / "legal_data"


class DomainRoutingError(RuntimeError):
    pass


class LegalDomain(str, Enum):
    INTELLECTUAL_PROPERTY = "INTELLECTUAL_PROPERTY"
    ENTERPRISE_COMPLIANCE = "ENTERPRISE_COMPLIANCE"
    LABOR_DISPUTE = "LABOR_DISPUTE"
    CROSS_DOMAIN = "CROSS_DOMAIN"
    UNMAPPED = "UNMAPPED"


class IssueDomainRoute(BaseModel):
    router_version: str = DOMAIN_ROUTER_VERSION
    domain: LegalDomain
    eligible_pack_ids: list[str] = Field(min_length=1)
    eligible_authority_ids: list[str] = Field(min_length=1)
    retrieval_authority_ids: list[str] = Field(default_factory=list)
    scope_applied: bool = True
    matched_signals: list[str] = Field(default_factory=list)
    fallback_all_ready_packs: bool = False
    reason: str


_DOMAIN_TAGS = {
    LegalDomain.INTELLECTUAL_PROPERTY: "intellectual-property",
    LegalDomain.ENTERPRISE_COMPLIANCE: "enterprise-compliance",
    LegalDomain.LABOR_DISPUTE: "labor-dispute",
}

_DOMAIN_SIGNALS: dict[LegalDomain, tuple[str, ...]] = {
    LegalDomain.INTELLECTUAL_PROPERTY: (
        "知识产权",
        "专利",
        "商标",
        "著作权",
        "版权",
        "发明",
        "专有技术",
        "技术成果",
    ),
    LegalDomain.ENTERPRISE_COMPLIANCE: (
        "公司治理",
        "公司法",
        "股东",
        "董事",
        "监事",
        "反垄断",
        "不正当竞争",
        "经营者集中",
        "数据安全",
        "个人信息",
        "网络安全",
        "数据出境",
        "商业秘密",
        "企业合规",
    ),
    LegalDomain.LABOR_DISPUTE: (
        "劳动合同",
        "劳动争议",
        "劳动仲裁",
        "劳动关系",
        "工资",
        "加班",
        "工时",
        "休息休假",
        "经济补偿",
        "社会保险",
        "社保",
        "用工",
        "竞业限制",
        "工伤",
        "试用期",
    ),
}


def _issue_text(issue: AuditPlanIssue) -> str:
    parts = [issue.topic]
    parts.extend(issue.why_review)
    parts.extend(issue.questions)
    parts.extend(issue.retrieval_queries)
    parts.extend(issue.legacy_hint_topics)
    return "\n".join(part for part in parts if part)


def _ready_packs(corpus_root: Path) -> dict[str, LoadedCorpusPack]:
    try:
        discovered = discover_corpus_packs(corpus_root)
    except CorpusPackError as exc:
        raise DomainRoutingError(f"Unable to load Corpus Packs for domain routing: {exc}") from exc
    ready = {
        item.manifest.pack_id: item
        for item in discovered
        if item.manifest.status == CorpusPackStatus.READY
    }
    if not ready:
        raise DomainRoutingError("Domain-aware retrieval requires at least one READY Corpus Pack.")
    return ready


def routing_catalog_fingerprint(corpus_root: Path = DEFAULT_CORPUS_ROOT) -> str:
    ready = _ready_packs(corpus_root)
    payload = []
    for pack_id in sorted(ready):
        pack = ready[pack_id]
        payload.append(
            {
                "pack_id": pack.manifest.pack_id,
                "pack_version": pack.manifest.pack_version,
                "domain_tags": sorted(pack.manifest.domain_tags),
                "members": sorted(
                    f"{member.authority_id}:{member.version_id}" for member in pack.members
                ),
            }
        )
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _pack_authorities(packs: list[LoadedCorpusPack]) -> list[str]:
    return sorted({member.authority_id for pack in packs for member in pack.members})


def _required_packs(
    ready: dict[str, LoadedCorpusPack], domains: list[LegalDomain]
) -> list[LoadedCorpusPack]:
    required_tags = {_DOMAIN_TAGS[domain] for domain in domains}
    selected = [
        ready[pack_id]
        for pack_id in sorted(ready)
        if required_tags & set(ready[pack_id].manifest.domain_tags)
    ]
    covered_tags = {
        tag
        for pack in selected
        for tag in pack.manifest.domain_tags
        if tag in required_tags
    }
    missing = sorted(required_tags - covered_tags)
    if missing:
        raise DomainRoutingError(
            "Required READY Corpus Pack domain tag(s) are unavailable for routing: " + ", ".join(missing)
        )
    return selected


def route_issue_to_corpus_packs(
    issue: AuditPlanIssue,
    contract_type: ContractType,
    *,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
) -> IssueDomainRoute:
    """Map one AuditPlan Issue to READY Corpus Packs without changing the Issue topology.

    Explicit lexical signals win. Multiple matched domains are preserved as a cross-domain
    union. Contract type is a deterministic fallback only when the Issue itself has no
    domain signal. Truly unmapped Issues use all READY packs to preserve recall rather than
    silently concluding that no law applies.
    """

    ready = _ready_packs(corpus_root)
    text = _issue_text(issue)
    matches: dict[LegalDomain, list[str]] = {}
    for domain, signals in _DOMAIN_SIGNALS.items():
        found = [signal for signal in signals if signal in text]
        if found:
            matches[domain] = found

    matched_domains = sorted(matches, key=lambda item: item.value)
    matched_signals = sorted({signal for values in matches.values() for signal in values})

    if len(matched_domains) == 1:
        domain = matched_domains[0]
        selected = _required_packs(ready, [domain])
        reason = f"Issue text matched deterministic {domain.value} signals."
        fallback = False
    elif len(matched_domains) > 1:
        domain = LegalDomain.CROSS_DOMAIN
        selected = _required_packs(ready, matched_domains)
        reason = "Issue text matched multiple legal domains; eligible packs are the deterministic union."
        fallback = False
    elif contract_type == ContractType.EMPLOYMENT:
        domain = LegalDomain.LABOR_DISPUTE
        selected = _required_packs(ready, [LegalDomain.LABOR_DISPUTE])
        reason = "No Issue-level domain signal matched; EMPLOYMENT contract type selected the labor-dispute domain."
        fallback = False
    elif contract_type == ContractType.EQUITY:
        domain = LegalDomain.ENTERPRISE_COMPLIANCE
        selected = _required_packs(ready, [LegalDomain.ENTERPRISE_COMPLIANCE])
        reason = "No Issue-level domain signal matched; EQUITY contract type selected the enterprise-compliance domain."
        fallback = False
    elif contract_type == ContractType.TECHNOLOGY:
        domain = LegalDomain.CROSS_DOMAIN
        selected = _required_packs(
            ready,
            [LegalDomain.INTELLECTUAL_PROPERTY, LegalDomain.ENTERPRISE_COMPLIANCE],
        )
        reason = "No Issue-level domain signal matched; TECHNOLOGY contract type selected IP + enterprise domains."
        fallback = False
    else:
        domain = LegalDomain.UNMAPPED
        selected = [ready[pack_id] for pack_id in sorted(ready)]
        reason = "No deterministic domain signal matched; all READY packs remain eligible to preserve retrieval recall."
        fallback = True

    eligible_pack_ids = sorted(pack.manifest.pack_id for pack in selected)
    eligible_authority_ids = _pack_authorities(selected)
    if not eligible_authority_ids:
        raise DomainRoutingError("Selected Corpus Packs contain no Authority members.")

    return IssueDomainRoute(
        domain=domain,
        eligible_pack_ids=eligible_pack_ids,
        eligible_authority_ids=eligible_authority_ids,
        retrieval_authority_ids=eligible_authority_ids,
        scope_applied=True,
        matched_signals=matched_signals,
        fallback_all_ready_packs=fallback,
        reason=reason,
    )
