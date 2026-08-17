from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import UUID

from pydantic import ValidationError

from .audit_plan_models import (
    AuditPlan,
    AuditPlanIssue,
    AuditPlanSource,
    AuditPlannerInput,
    ContractType,
    ModelAuditPlanDraft,
    PlannerContractItem,
    PlannerRuleHint,
    PlannerTopicHint,
    ReviewPriority,
)
from .audit_planner_provider import AuditPlannerProvider, planner_provider_from_name
from .audit_rule_models import AuditRuleReport, RuleState
from .audit_rules import AuditRuleProcessingError, load_audit_rule_report
from .audit_topic_hints import LEGACY_TOPIC_HINTS
from .contract_models import CanonicalContract
from .contract_structure import StructureProcessingError, load_contract_structure
from .pipeline_control import begin_provider_call, ensure_pipeline_control, finish_provider_call
from .pipeline_control_models import ProviderExecutionMode
from .safe_persistence import atomic_write_text
from .storage import job_audit_plan_path

DIRECT_PLANNER_TEXT_CHAR_LIMIT = 60_000
MAX_RETRIEVAL_QUERY_CHARS = 300


class AuditPlannerError(RuntimeError):
    pass


class AuditPlannerValidationError(AuditPlannerError):
    pass


class AuditPlannerSizeError(AuditPlannerError):
    code = "HIERARCHICAL_PLANNING_REQUIRED"

    def __init__(self, total_text_chars: int) -> None:
        self.total_text_chars = total_text_chars
        self.direct_text_char_limit = DIRECT_PLANNER_TEXT_CHAR_LIMIT
        super().__init__(
            f"Contract canonical text has {total_text_chars} characters, above the direct Planner budget "
            f"of {DIRECT_PLANNER_TEXT_CHAR_LIMIT}. Stage 13C hierarchical planning is required; Law-Rag did not truncate the contract."
        )


@dataclass(frozen=True)
class BaselineIssueSpec:
    topic: str
    priority: ReviewPriority
    questions: tuple[str, ...]
    retrieval_queries: tuple[str, ...]


def _spec(topic: str, question: str, query: str, priority: ReviewPriority = ReviewPriority.NORMAL) -> BaselineIssueSpec:
    return BaselineIssueSpec(topic, priority, (question,), (query,))


GENERAL_BASELINE: tuple[BaselineIssueSpec, ...] = (
    _spec("合同主体与授权", "当事人身份、签约主体及授权安排是否明确且前后一致？", "合同 当事人 签约主体 授权"),
    _spec("交易标的与范围", "交易标的、数量、范围或服务边界是否足够明确？", "合同 标的 数量 服务范围 明确"),
    _spec("价款与结算", "价款、支付触发条件、期限、税费和结算安排是否明确且相互一致？", "合同 价款 支付 结算 税费"),
    _spec("履行与交付", "履行时间、地点、方式、交付义务及协作义务是否明确？", "合同 履行 交付 时间 地点 协作"),
    _spec("质量与验收", "质量标准、验收主体、程序、期限及不合格处理是否明确？", "合同 质量标准 验收 检验 不合格"),
    _spec("期限与生效", "合同期限、生效条件、续展和关键日期安排是否清楚？", "合同 期限 生效 条件 续展"),
    _spec("违约责任", "主要违约情形、责任承担、损失赔偿和违约金安排是否完整且协调？", "合同 违约责任 赔偿损失 违约金"),
    _spec("变更解除与终止", "变更、解除、终止的触发条件、程序及后果是否明确？", "合同 变更 解除 终止 后果"),
    _spec("不可抗力与风险事件", "不可抗力及其他风险事件的通知、减损和后果分配是否明确？", "合同 不可抗力 通知 减损 风险分配"),
    _spec("保密知识产权与数据", "保密、知识产权、成果归属和数据处理安排是否与交易相匹配？", "合同 保密 知识产权 成果归属 数据"),
    _spec("争议解决", "适用法律、管辖、仲裁或争议解决条款是否明确且相互一致？", "合同 争议解决 管辖 仲裁"),
    _spec("通知附件与文件优先级", "通知方式、附件引用、文件组成及冲突时的优先顺序是否明确？", "合同 通知 附件 文件优先顺序"),
)

TYPE_SPECIFIC: dict[ContractType, tuple[BaselineIssueSpec, ...]] = {
    ContractType.PURCHASE: (
        _spec("所有权与风险转移", "标的物所有权及毁损灭失风险何时转移？", "买卖合同 所有权 风险转移"),
        _spec("质保与售后", "质量保证期、维修更换及售后责任是否明确？", "买卖合同 质量保证 维修 更换"),
    ),
    ContractType.SERVICE: (
        _spec("服务标准与SLA", "服务成果、服务标准、响应时限或SLA是否可验证？", "服务合同 服务标准 SLA 履行"),
        _spec("人员与分包", "关键人员、更换人员、转委托或分包限制是否明确？", "服务合同 转委托 分包 人员"),
    ),
    ContractType.LEASE: (
        _spec("租赁物权属与用途", "租赁物权属、交付状态、约定用途及限制是否明确？", "租赁合同 租赁物 权属 用途"),
        _spec("押金维修与返还", "押金、维修责任、费用承担和返还条件是否明确？", "租赁合同 押金 维修 返还"),
        _spec("转租与提前退租", "转租限制及提前解除、退租后果是否明确？", "租赁合同 转租 解除 返还"),
    ),
    ContractType.EMPLOYMENT: (
        _spec("岗位工时与工作地点", "岗位职责、工作地点、工时及调整机制是否明确？", "劳动合同 工作内容 工作地点 工作时间"),
        _spec("薪酬福利与试用期", "工资、奖金、福利、试用期及支付条件是否明确？", "劳动合同 工资 试用期 福利"),
        _spec("解除离职与限制义务", "解除、离职、保密、竞业限制及经济补偿安排是否需要重点审查？", "劳动合同 解除 竞业限制 经济补偿"),
    ),
    ContractType.CONSTRUCTION: (
        _spec("工程范围与工期", "工程范围、开竣工、工期顺延及关键节点是否明确？", "建设工程 工程范围 工期 顺延"),
        _spec("工程价款与变更签证", "计价方式、进度款、结算、设计变更和签证机制是否明确？", "建设工程 价款 结算 变更 签证"),
        _spec("质量验收与保修", "质量标准、竣工验收、缺陷责任和保修安排是否完整？", "建设工程 质量 验收 保修"),
        _spec("安全与分包", "安全责任、分包转包和现场管理责任是否明确？", "建设工程 安全 分包 转包"),
    ),
    ContractType.TECHNOLOGY: (
        _spec("技术成果与知识产权", "背景知识产权、开发成果、许可范围和第三方权利风险是否明确？", "技术合同 技术成果 知识产权 许可"),
        _spec("技术交付与验收", "技术指标、里程碑、测试验收及缺陷修复标准是否明确？", "技术合同 技术指标 交付 验收"),
    ),
    ContractType.LOAN: (
        _spec("本金利息与还款", "本金、利率、计息、还款计划及提前还款安排是否明确？", "借款合同 本金 利率 还款"),
        _spec("担保与加速到期", "担保、违约事件及提前到期机制是否明确？", "借款合同 担保 违约 提前到期"),
    ),
    ContractType.EQUITY: (
        _spec("交易标的与交割", "股权范围、价格、支付、先决条件和交割步骤是否明确？", "股权转让 交易价款 先决条件 交割"),
        _spec("陈述保证与赔偿", "陈述保证、披露、赔偿和责任限制机制是否完整？", "股权交易 陈述保证 赔偿 责任限制"),
        _spec("治理与权利限制", "表决、分红、优先权、转让限制或退出安排是否需要审查？", "股权协议 公司治理 转让限制 退出"),
    ),
}


def baseline_for(contract_type: ContractType) -> tuple[BaselineIssueSpec, ...]:
    return GENERAL_BASELINE + TYPE_SPECIFIC.get(contract_type, ())


def _unique(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _object_text(contract: CanonicalContract) -> list[PlannerContractItem]:
    items: list[PlannerContractItem] = []
    for clause in contract.clauses:
        text = "\n".join(part for part in (clause.heading_token, clause.heading_text, clause.body_text) if part).strip()
        items.append(
            PlannerContractItem(
                canonical_object_id=clause.clause_id,
                object_type="CLAUSE",
                text=text,
                evidence_ids=_unique(eid for span in clause.source_spans for eid in span.evidence_ids),
            )
        )
    for block in contract.unnumbered_blocks:
        items.append(
            PlannerContractItem(
                canonical_object_id=block.block_id,
                object_type="UNNUMBERED_BLOCK",
                text=block.text,
                evidence_ids=_unique(eid for span in block.source_spans for eid in span.evidence_ids),
            )
        )
    return items


def _legacy_hints(items: list[PlannerContractItem]) -> list[PlannerTopicHint]:
    output: list[PlannerTopicHint] = []
    for hint in LEGACY_TOPIC_HINTS:
        ids = [item.canonical_object_id for item in items if hint.pattern.search(item.text)]
        if ids:
            output.append(
                PlannerTopicHint(
                    topic=hint.topic,
                    retrieval_query=hint.retrieval_query,
                    contract_object_ids=_unique(ids),
                )
            )
    return sorted(output, key=lambda item: item.topic)


def _rule_hints(rules: AuditRuleReport) -> list[PlannerRuleHint]:
    output: list[PlannerRuleHint] = []
    for result in rules.results:
        if result.state not in {RuleState.FAIL, RuleState.REVIEW}:
            continue
        output.append(
            PlannerRuleHint(
                result_id=result.result_id,
                rule_id=result.rule_id,
                state=result.state.value,
                reason_code=result.reason_code,
                title=result.title,
                explanation=result.explanation,
                canonical_object_ids=result.canonical_object_ids,
            )
        )
    return sorted(output, key=lambda item: item.result_id)


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_planner_input(job_id: UUID) -> AuditPlannerInput:
    try:
        contract = load_contract_structure(job_id)
    except (FileNotFoundError, StructureProcessingError) as exc:
        raise AuditPlannerError("Canonical contract structure is required before Audit Planner.") from exc
    try:
        rules = load_audit_rule_report(job_id)
    except (FileNotFoundError, AuditRuleProcessingError) as exc:
        raise AuditPlannerError("Deterministic audit-rules.json is required before Audit Planner.") from exc

    items = _object_text(contract)
    total_text_chars = sum(len(item.text) for item in items)
    if total_text_chars > DIRECT_PLANNER_TEXT_CHAR_LIMIT:
        raise AuditPlannerSizeError(total_text_chars)

    rule_hints = _rule_hints(rules)
    topic_hints = _legacy_hints(items)
    base = {
        "job_id": str(job_id),
        "contract_schema_version": contract.schema_version,
        "contract_source_fingerprint": contract.source_fingerprint,
        "contract_content_fingerprint": rules.contract_content_fingerprint,
        "contract_items": [item.model_dump(mode="json") for item in items],
        "deterministic_rule_hints": [item.model_dump(mode="json") for item in rule_hints],
        "legacy_topic_hints": [item.model_dump(mode="json") for item in topic_hints],
        "total_text_chars": total_text_chars,
    }
    return AuditPlannerInput(**base, input_fingerprint=_fingerprint(base))


def _normalize_topic(value: str) -> str:
    return "".join(value.lower().split())


def _clean_nonempty(values: Iterable[str], *, label: str, max_chars: int | None = None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        if not value:
            raise AuditPlannerValidationError(f"Planner produced an empty {label}.")
        if max_chars is not None and len(value) > max_chars:
            raise AuditPlannerValidationError(f"Planner {label} exceeds {max_chars} characters.")
        key = " ".join(value.split()).lower()
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _priority_max(left: ReviewPriority, right: ReviewPriority) -> ReviewPriority:
    rank = {ReviewPriority.NORMAL: 0, ReviewPriority.IMPORTANT: 1, ReviewPriority.HIGH_ATTENTION: 2}
    return left if rank[left] >= rank[right] else right


def _stable_issue_id(topic: str) -> str:
    return "plan-" + hashlib.sha256(_normalize_topic(topic).encode("utf-8")).hexdigest()[:16]


def _evidence_for(object_ids: list[str], object_map: dict[str, PlannerContractItem]) -> list[str]:
    return _unique(eid for object_id in object_ids for eid in object_map[object_id].evidence_ids)


def merge_audit_plan(planner_input: AuditPlannerInput, draft: ModelAuditPlanDraft, provider_result) -> AuditPlan:
    object_map = {item.canonical_object_id: item for item in planner_input.contract_items}
    issues: dict[str, AuditPlanIssue] = {}

    def upsert(
        *,
        topic: str,
        priority: ReviewPriority,
        source: AuditPlanSource,
        why_review: Iterable[str],
        contract_object_ids: Iterable[str] = (),
        questions: Iterable[str] = (),
        retrieval_queries: Iterable[str] = (),
        rule_result_ids: Iterable[str] = (),
        legacy_hint_topics: Iterable[str] = (),
    ) -> None:
        topic_clean = topic.strip()
        if not topic_clean:
            raise AuditPlannerValidationError("Planner produced an empty issue topic.")
        why_values = [item.strip() for item in why_review if item.strip()]
        object_values = [item.strip() for item in contract_object_ids if item.strip()]
        question_values = list(questions)
        query_values = list(retrieval_queries)
        rule_values = list(rule_result_ids)
        legacy_values = list(legacy_hint_topics)

        object_ids = _unique(object_values)
        unknown = [value for value in object_ids if value not in object_map]
        if unknown:
            raise AuditPlannerValidationError(
                "Planner referenced unknown canonical object ID(s): " + ", ".join(sorted(unknown))
            )
        cleaned_questions = _clean_nonempty(question_values, label="review question") if question_values else []
        cleaned_queries = (
            _clean_nonempty(query_values, label="retrieval query", max_chars=MAX_RETRIEVAL_QUERY_CHARS)
            if query_values
            else []
        )
        key = _normalize_topic(topic_clean)
        existing = issues.get(key)
        if existing is None:
            issues[key] = AuditPlanIssue(
                issue_id=_stable_issue_id(topic_clean),
                topic=topic_clean,
                priority=priority,
                sources=[source],
                why_review=_unique(why_values),
                contract_object_ids=object_ids,
                contract_evidence_ids=_evidence_for(object_ids, object_map),
                questions=cleaned_questions,
                retrieval_queries=cleaned_queries,
                rule_result_ids=_unique(rule_values),
                legacy_hint_topics=_unique(legacy_values),
            )
            return
        existing.priority = _priority_max(existing.priority, priority)
        existing.sources = list(dict.fromkeys([*existing.sources, source]))
        existing.why_review = _unique([*existing.why_review, *why_values])
        existing.contract_object_ids = _unique([*existing.contract_object_ids, *object_ids])
        existing.contract_evidence_ids = _evidence_for(existing.contract_object_ids, object_map)
        existing.questions = _unique([*existing.questions, *cleaned_questions])
        existing.retrieval_queries = _unique([*existing.retrieval_queries, *cleaned_queries])
        existing.rule_result_ids = _unique([*existing.rule_result_ids, *rule_values])
        existing.legacy_hint_topics = _unique([*existing.legacy_hint_topics, *legacy_values])

    for item in baseline_for(draft.contract_type):
        upsert(
            topic=item.topic,
            priority=item.priority,
            source=AuditPlanSource.BASELINE,
            why_review=["Baseline checklist coverage; this topic must be reviewed even if the Planner did not flag a specific risk."],
            questions=item.questions,
            retrieval_queries=item.retrieval_queries,
        )

    for hint in planner_input.deterministic_rule_hints:
        upsert(
            topic=f"确定性异常：{hint.title}",
            priority=ReviewPriority.HIGH_ATTENTION if hint.state == RuleState.FAIL.value else ReviewPriority.IMPORTANT,
            source=AuditPlanSource.DETERMINISTIC_HINT,
            why_review=[hint.explanation],
            contract_object_ids=hint.canonical_object_ids,
            questions=[f"确定性检查 {hint.rule_id} 的异常是否反映了需要进一步审查的合同风险？"],
            retrieval_queries=[f"合同 {hint.title} {hint.reason_code}"],
            rule_result_ids=[hint.result_id],
        )

    for hint in planner_input.legacy_topic_hints:
        upsert(
            topic=hint.topic,
            priority=ReviewPriority.IMPORTANT,
            source=AuditPlanSource.DETERMINISTIC_HINT,
            why_review=["Legacy keyword router matched this topic; it is retained only as a deterministic hint."],
            contract_object_ids=hint.contract_object_ids,
            questions=[f"与“{hint.topic}”相关的条款是否存在需要结合适用法律进一步审查的问题？"],
            retrieval_queries=[hint.retrieval_query],
            legacy_hint_topics=[hint.topic],
        )

    for dynamic in draft.issues:
        if not dynamic.questions:
            raise AuditPlannerValidationError(f"Dynamic issue {dynamic.client_issue_id} has no review questions.")
        if not dynamic.retrieval_queries:
            raise AuditPlannerValidationError(f"Dynamic issue {dynamic.client_issue_id} has no retrieval queries.")
        upsert(
            topic=dynamic.topic,
            priority=dynamic.priority,
            source=AuditPlanSource.LLM_DYNAMIC,
            why_review=[dynamic.why_review],
            contract_object_ids=dynamic.contract_object_ids,
            questions=dynamic.questions,
            retrieval_queries=dynamic.retrieval_queries,
        )

    warnings: list[str] = []
    if draft.contract_type in {ContractType.UNKNOWN, ContractType.MIXED}:
        warnings.append(
            "Planner did not select one specific contract type; Law-Rag applied the conservative GENERAL baseline checklist."
        )
    warnings.append(
        "Stage 13B creates review scope only. Final legal conclusions remain disabled until later issue-based retrieval/audit stages."
    )

    priority_rank = {ReviewPriority.HIGH_ATTENTION: 0, ReviewPriority.IMPORTANT: 1, ReviewPriority.NORMAL: 2}
    return AuditPlan(
        job_id=planner_input.job_id,
        contract_type=draft.contract_type,
        contract_type_confidence=draft.contract_type_confidence,
        contract_type_reasoning=draft.contract_type_reasoning,
        provider=provider_result.provider,
        model=provider_result.model,
        contract_source_fingerprint=planner_input.contract_source_fingerprint,
        contract_content_fingerprint=planner_input.contract_content_fingerprint,
        planner_input_fingerprint=planner_input.input_fingerprint,
        planner_response_hash=provider_result.raw_response_hash,
        provider_request_id=provider_result.request_id,
        provider_finish_reason=provider_result.finish_reason,
        provider_usage=provider_result.usage,
        issues=sorted(issues.values(), key=lambda item: (priority_rank[item.priority], item.topic, item.issue_id)),
        warnings=warnings,
    )


def run_audit_planner(
    job_id: UUID,
    *,
    provider_name: str = "deepseek",
    provider: AuditPlannerProvider | None = None,
) -> AuditPlan:
    planner_input = build_planner_input(job_id)
    selected = provider or planner_provider_from_name(provider_name)

    # Planner is the first external model step in the new architecture. New jobs
    # without explicit control fail closed to REQUIRE_APPROVAL; existing explicit
    # AUTO/LOCAL policies remain authoritative.
    ensure_pipeline_control(job_id, ProviderExecutionMode.REQUIRE_APPROVAL)
    boundary_name = f"{selected.provider_name}-planner"
    begin_provider_call(job_id, boundary_name)
    try:
        provider_result = selected.generate(planner_input)
    finally:
        finish_provider_call(job_id, boundary_name)

    try:
        draft = ModelAuditPlanDraft.model_validate_json(provider_result.content)
    except ValidationError as exc:
        raise AuditPlannerValidationError("Planner returned JSON that does not match the strict AuditPlan draft schema.") from exc

    plan = merge_audit_plan(planner_input, draft, provider_result)
    atomic_write_text(Path(job_audit_plan_path(job_id)), plan.model_dump_json(indent=2))
    return plan


def load_audit_plan(job_id: UUID) -> AuditPlan:
    path = job_audit_plan_path(job_id)
    if not path.exists():
        raise FileNotFoundError(f"Audit Plan for job {job_id} does not exist.")
    try:
        plan = AuditPlan.model_validate_json(path.read_bytes())
    except Exception as exc:
        raise AuditPlannerError("Persisted audit-plan.json is malformed and cannot be loaded safely.") from exc
    if plan.job_id != job_id:
        raise AuditPlannerError("Persisted audit-plan.json belongs to a different job ID.")
    return plan
