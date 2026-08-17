from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditTopicHint:
    topic: str
    pattern: re.Pattern[str]
    retrieval_query: str


# Legacy Stage 8 keyword topics are retained as deterministic hints only.
# Stage 13D will stop using them as the authoritative retrieval/audit scope.
LEGACY_TOPIC_HINTS: tuple[AuditTopicHint, ...] = (
    AuditTopicHint(
        topic="格式条款",
        pattern=re.compile(r"格式条款|免责|免除.{0,12}责任|减轻.{0,12}责任|限制.{0,12}权利|排除.{0,12}权利"),
        retrieval_query="格式条款 提示说明义务 免除减轻责任 限制排除主要权利",
    ),
    AuditTopicHint(
        topic="违约金",
        pattern=re.compile(r"违约金"),
        retrieval_query="违约金 过分高于损失 调整",
    ),
    AuditTopicHint(
        topic="定金",
        pattern=re.compile(r"定金"),
        retrieval_query="定金 主合同标的额 百分之二十",
    ),
    AuditTopicHint(
        topic="合同生效",
        pattern=re.compile(r"合同生效|生效日期|批准|审批"),
        retrieval_query="合同生效 批准手续",
    ),
    AuditTopicHint(
        topic="合同履行",
        pattern=re.compile(r"全面履行|履行义务|通知|协助|保密"),
        retrieval_query="合同全面履行 诚信 通知 协助 保密",
    ),
    AuditTopicHint(
        topic="违约责任",
        pattern=re.compile(r"违约责任|不履行|补救措施|赔偿损失"),
        retrieval_query="不履行合同义务 继续履行 补救措施 赔偿损失",
    ),
    AuditTopicHint(
        topic="合同形式",
        pattern=re.compile(r"书面形式|电子邮件|数据电文|传真|电报"),
        retrieval_query="合同书面形式 数据电文 电子邮件",
    ),
    AuditTopicHint(
        topic="合同成立",
        pattern=re.compile(r"合同成立|标的和数量"),
        retrieval_query="合同成立 当事人名称 标的 数量",
    ),
)
