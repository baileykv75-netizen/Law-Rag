from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from .ai_audit_models import (
    AuditContextPackage,
    AuditIssuePackage,
    ContractContextItem,
    RuleContextItem,
)
from .audit_rule_models import RuleState
from .audit_rules import AuditRuleProcessingError, load_audit_rule_report
from .contract_models import CanonicalContract, Clause, SourceSpan
from .contract_structure import StructureProcessingError, load_contract_structure
from .legal.retrieval import get_retrieval_index_summary, retrieve_legal_evidence
from .legal.retrieval_models import RetrievalRequest
from .storage import legal_db_path, legal_retrieval_index_path


class AiAuditContextError(RuntimeError):
    pass


QUERY_METHOD = "stage8-keyword-map-v1"


@dataclass(frozen=True)
class TopicRule:
    topic: str
    pattern: re.Pattern[str]
    query: str


TOPIC_RULES = [
    TopicRule(
        topic="格式条款",
        pattern=re.compile(r"格式条款|免责|免除.{0,12}责任|减轻.{0,12}责任|限制.{0,12}权利|排除.{0,12}权利"),
        query="格式条款 提示说明义务 免除减轻责任 限制排除主要权利",
    ),
    TopicRule(
        topic="违约金",
        pattern=re.compile(r"违约金"),
        query="违约金 过分高于损失 调整",
    ),
    TopicRule(
        topic="定金",
        pattern=re.compile(r"定金"),
        query="定金 主合同标的额 百分之二十",
    ),
    TopicRule(
        topic="合同生效",
        pattern=re.compile(r"合同生效|生效日期|批准|审批"),
        query="合同生效 批准手续",
    ),
    TopicRule(
        topic="合同履行",
        pattern=re.compile(r"全面履行|履行义务|通知|协助|保密"),
        query="合同全面履行 诚信 通知 协助 保密",
    ),
    TopicRule(
        topic="违约责任",
        pattern=re.compile(r"违约责任|不履行|补救措施|赔偿损失"),
        query="不履行合同义务 继续履行 补救措施 赔偿损失",
    ),
    TopicRule(
        topic="合同形式",
        pattern=re.compile(r"书面形式|电子邮件|数据电文|传真|电报"),
        query="合同书面形式 数据电文 电子邮件",
    ),
    TopicRule(
        topic="合同成立",
        pattern=re.compile(r"合同成立|标的和数量"),
        query="合同成立 当事人名称 标的 数量",
    ),
]


def _evidence_ids(spans: list[SourceSpan]) -> list[str]:
    return list(dict.fromkeys(evidence_id for span in spans for evidence_id in span.evidence_ids))


def _clause_text(clause: Clause) -> str:
    parts = [clause.heading_token, clause.heading_text, clause.body_text]
    return "\n".join(part for part in parts if part).strip()


def _issue_id(topic: str, object_ids: list[str], query: str) -> str:
    payload = json.dumps(
        {"topic": topic, "object_ids": sorted(object_ids), "query": query},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "issue-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _contract_item(clause: Clause) -> ContractContextItem:
    return ContractContextItem(
        canonical_object_id=clause.clause_id,
        object_type="CLAUSE",
        text=_clause_text(clause),
        source_spans=clause.source_spans,
        evidence_ids=_evidence_ids(clause.source_spans),
    )


def _fingerprint_payload(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_prerequisites(job_id: UUID) -> tuple[CanonicalContract, object]:
    try:
        contract = load_contract_structure(job_id)
    except (FileNotFoundError, StructureProcessingError) as exc:
        raise AiAuditContextError("Stage 4 contract.json is required before primary AI audit.") from exc
    try:
        rules = load_audit_rule_report(job_id)
    except (FileNotFoundError, AuditRuleProcessingError) as exc:
        raise AiAuditContextError("Stage 5 audit-rules.json is required before primary AI audit.") from exc
    index_summary = get_retrieval_index_summary(legal_retrieval_index_path(), legal_db_path())
    if not index_summary.ready or not index_summary.lexical_ready:
        raise AiAuditContextError(
            "Stage 7 retrieval index is not ready. Build the legal seed and retrieval index before primary AI audit."
        )
    return contract, rules


def build_audit_context(
    job_id: UUID,
    *,
    as_of: date,
    use_semantic: bool = False,
) -> AuditContextPackage:
    contract, rules = _load_prerequisites(job_id)

    topic_matches: dict[str, tuple[TopicRule, list[Clause]]] = {}
    for clause in contract.clauses:
        text = _clause_text(clause)
        for topic_rule in TOPIC_RULES:
            if topic_rule.pattern.search(text):
                current = topic_matches.setdefault(topic_rule.topic, (topic_rule, []))[1]
                current.append(clause)

    contract_items_by_id: dict[str, ContractContextItem] = {}
    issues: list[AuditIssuePackage] = []
    warnings: list[str] = []

    for topic in sorted(topic_matches):
        topic_rule, clauses = topic_matches[topic]
        object_ids = [clause.clause_id for clause in clauses]
        evidence_ids = list(
            dict.fromkeys(evidence_id for clause in clauses for evidence_id in _evidence_ids(clause.source_spans))
        )
        for clause in clauses:
            contract_items_by_id.setdefault(clause.clause_id, _contract_item(clause))
        retrieval = retrieve_legal_evidence(
            legal_db_path(),
            legal_retrieval_index_path(),
            RetrievalRequest(
                query=topic_rule.query,
                as_of=as_of,
                top_k=5,
                use_semantic=use_semantic,
            ),
        )
        issue = AuditIssuePackage(
            issue_id=_issue_id(topic_rule.topic, object_ids, topic_rule.query),
            topic=topic_rule.topic,
            query_method=QUERY_METHOD,
            retrieval_query=topic_rule.query,
            contract_object_ids=object_ids,
            contract_evidence_ids=evidence_ids,
            retrieval=retrieval,
        )
        issues.append(issue)
        warnings.extend(f"{topic_rule.topic}: {item}" for item in retrieval.warnings)

    if not issues:
        warnings.append(
            "No deterministic Stage 8 legal topic matched the canonical clauses. The model must not invent an unsupported legal issue."
        )

    rule_items: list[RuleContextItem] = []
    for result in rules.results:
        if result.state == RuleState.PASS:
            continue
        rule_items.append(
            RuleContextItem(
                result_id=result.result_id,
                rule_id=result.rule_id,
                state=result.state.value,
                reason_code=result.reason_code,
                explanation=result.explanation,
                canonical_object_ids=result.canonical_object_ids,
                evidence_ids=result.evidence_ids,
                source_spans=result.source_spans,
                review_reasons=result.review_reasons,
            )
        )

    base_payload = {
        "schema_version": "1.0.0",
        "builder_version": "stage8-context-1.0.0",
        "job_id": str(job_id),
        "as_of": as_of.isoformat(),
        "contract_schema_version": contract.schema_version,
        "contract_source_fingerprint": contract.source_fingerprint,
        "contract_content_fingerprint": rules.contract_content_fingerprint,
        "contract_items": [
            item.model_dump(mode="json") for item in sorted(contract_items_by_id.values(), key=lambda item: item.canonical_object_id)
        ],
        "rule_items": [item.model_dump(mode="json") for item in sorted(rule_items, key=lambda item: item.result_id)],
        "issues": [item.model_dump(mode="json") for item in sorted(issues, key=lambda item: item.issue_id)],
        "warnings": sorted(set(warnings)),
    }
    context_fingerprint = _fingerprint_payload(base_payload)
    return AuditContextPackage(
        job_id=job_id,
        as_of=as_of,
        contract_schema_version=contract.schema_version,
        contract_source_fingerprint=contract.source_fingerprint,
        contract_content_fingerprint=rules.contract_content_fingerprint,
        contract_items=sorted(contract_items_by_id.values(), key=lambda item: item.canonical_object_id),
        rule_items=sorted(rule_items, key=lambda item: item.result_id),
        issues=sorted(issues, key=lambda item: item.issue_id),
        warnings=sorted(set(warnings)),
        context_fingerprint=context_fingerprint,
    )
