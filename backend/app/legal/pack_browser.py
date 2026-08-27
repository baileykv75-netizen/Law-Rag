from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.storage import legal_db_path, legal_last_import_report_path, legal_retrieval_index_path, runtime_dir

from .corpus_packs import CorpusPackError, discover_corpus_packs
from .importer import import_manifest
from .models import LegalManifest, LegalStoreSummary
from .official_downloader import OfficialLegalDownloadError, download_npc_legal_manifest, has_official_text_source
from .retrieval import RetrievalIndexError, build_retrieval_index, get_retrieval_index_summary
from .store import get_summary, list_authorities, list_version_identities


REPO_ROOT = Path(__file__).resolve().parents[3]


def legal_data_root() -> Path:
    configured = os.getenv("LAW_RAG_LEGAL_DATA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        bundled = Path(bundle_root).resolve() / "legal_data"
        if bundled.exists():
            return bundled

    return REPO_ROOT / "legal_data"


def source_registry_path() -> Path:
    return legal_data_root() / "source_registry.json"


PackState = Literal["INSTALLED", "AVAILABLE", "DOWNLOADING", "FAILED", "ADAPTER_PENDING"]
DownloadState = Literal["INSTALLED", "FAILED", "UNAVAILABLE"]
DownloadTaskState = Literal["QUEUED", "RUNNING", "COMPLETE", "FAILED"]


class LegalPackSource(BaseModel):
    name: str
    url: str


class LegalPackTreeNode(BaseModel):
    pack_id: str
    display_name: str
    description: str
    state: PackState
    authority_count: int = Field(ge=0)
    installed_authority_count: int = Field(ge=0)
    law_refs: list[str] = Field(default_factory=list)
    adapter_note: str | None = None
    source_refs: list[LegalPackSource] = Field(default_factory=list)
    children: list["LegalPackTreeNode"] = Field(default_factory=list)


class LegalPackDownloadResponse(BaseModel):
    pack_id: str
    state: DownloadState
    message: str
    imported_records: int = Field(ge=0)
    no_change_records: int = Field(ge=0)
    rejected_records: int = Field(ge=0)
    rebuilt_index: bool
    summary: LegalStoreSummary


class LegalPackDownloadTask(BaseModel):
    task_id: UUID
    pack_id: str
    state: DownloadTaskState
    message: str
    progress_percent: int = Field(ge=0, le=100)
    started_at: datetime
    finished_at: datetime | None = None
    result: LegalPackDownloadResponse | None = None


@dataclass(frozen=True)
class PackDefinition:
    pack_id: str
    display_name: str
    description: str
    manifest_paths: tuple[str, ...] = ()
    law_refs: tuple[str, ...] = ()
    adapter_note: str | None = None
    source_refs: tuple[LegalPackSource, ...] = ()
    children: tuple["PackDefinition", ...] = ()


@dataclass(frozen=True)
class PackManifestResolution:
    manifest_paths: tuple[str, ...]
    unresolved_law_refs: tuple[str, ...]


OFFICIAL_SOURCES = (
    LegalPackSource(name="国家法律法规数据库", url="https://flk.npc.gov.cn/search"),
    LegalPackSource(name="司法部国家行政法规库", url="https://xzfg.moj.gov.cn/search2.html"),
    LegalPackSource(name="最高人民法院官网", url="https://www.court.gov.cn/"),
    LegalPackSource(name="最高人民法院公报", url="https://gongbao.court.gov.cn/"),
)

OPEN_SOURCE_REFERENCES = (
    LegalPackSource(name="cn-law-hub 适配参考", url="https://github.com/ZongziForu/cn-law-hub"),
    LegalPackSource(name="law-crawler-unified 适配参考", url="https://github.com/Li2zon3/law-crawler-unified"),
    LegalPackSource(name="lawtext/laws 数据结构参考", url="https://github.com/lawtext/laws"),
    LegalPackSource(name="law-datasets 清单参考", url="https://github.com/twang2218/law-datasets/blob/main/law-and-regulations/README.md"),
)

DEFAULT_ADAPTER_NOTE = "官方来源下载适配正在补充；当前可打开官方入口核验并后续接入自动下载。"

LOCAL_SNAPSHOT_HINTS = {
    "民法典": ("seed/manifest.json",),
    "合同编通则": ("seed/manifest.json",),
    "劳动法": ("authorities/prc-labor-law/effective-2018-12-29/manifest.json",),
    "劳动合同法": ("authorities/prc-labor-contract-law/effective-2013-07-01/manifest.json",),
    "社会保险法": ("authorities/prc-social-insurance-law/effective-2018-12-29/manifest.json",),
    "劳动争议调解仲裁法": (
        "authorities/prc-labor-dispute-mediation-arbitration-law/effective-2008-05-01/manifest.json",
    ),
    "审理劳动争议案件适用法律问题的解释（二）": (
        "authorities/spc-labor-dispute-interpretation-2/effective-2025-09-01/manifest.json",
    ),
    "公司法": ("authorities/prc-company-law/effective-2024-07-01/manifest.json",),
    "反垄断法": ("authorities/prc-anti-monopoly-law/effective-2022-08-01/manifest.json",),
    "反不正当竞争法": (
        "authorities/prc-anti-unfair-competition-law/effective-2025-10-15/manifest.json",
    ),
    "网络安全法": ("authorities/prc-cybersecurity-law/effective-2026-01-01/manifest.json",),
    "数据安全法": ("authorities/prc-data-security-law/effective-2021-09-01/manifest.json",),
    "个人信息保护法": (
        "authorities/prc-personal-information-protection-law/effective-2021-11-01/manifest.json",
    ),
    "专利法": ("authorities/prc-patent-law/effective-2021-06-01/manifest.json",),
    "商标法": (
        "authorities/prc-trademark-law/effective-2019-11-01/manifest.json",
        "authorities/prc-trademark-law/effective-2027-01-01/manifest.json",
    ),
    "著作权法": ("authorities/prc-copyright-law/effective-2021-06-01/manifest.json",),
    "建设工程合同": (
        "authorities/prc-civil-code-construction-contract-excerpt/effective-2021-01-01/manifest.json",
    ),
    "建筑法": ("authorities/prc-construction-law/effective-2019-04-23/manifest.json",),
    "建设工程质量管理条例": (
        "authorities/state-council-construction-quality-regulation/effective-2019-04-23/manifest.json",
    ),
    "建设工程司法解释": (
        "authorities/spc-construction-contract-interpretation-1/effective-2021-01-01/manifest.json",
    ),
    "建设工程施工合同纠纷": (
        "authorities/spc-construction-contract-interpretation-1/effective-2021-01-01/manifest.json",
    ),
}


PACK_TREE: tuple[PackDefinition, ...] = (
    PackDefinition(
        pack_id="cn-contract-general-core",
        display_name="通用合同基础",
        description="民法典合同编核心条款与合同编通则司法解释选摘，作为所有合同审查的基础法源。",
        manifest_paths=("seed/manifest.json",),
        law_refs=("中华人民共和国民法典（合同编）", "最高人民法院关于适用民法典合同编通则若干问题的解释"),
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-labor-dispute-core",
        display_name="劳动用工",
        description="劳动合同、劳动争议、社会保险和相关司法解释。",
        law_refs=("中华人民共和国劳动法", "中华人民共和国劳动合同法", "中华人民共和国社会保险法", "劳动争议司法解释"),
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-enterprise-compliance-core",
        display_name="企业合规与数据",
        description="公司治理、竞争合规、数据安全、个人信息保护和网络安全。",
        law_refs=("中华人民共和国公司法", "中华人民共和国反垄断法", "中华人民共和国反不正当竞争法", "中华人民共和国网络安全法", "中华人民共和国数据安全法", "中华人民共和国个人信息保护法"),
        source_refs=OFFICIAL_SOURCES,
        children=(
            PackDefinition(
                pack_id="cn-data-privacy-saas-core",
                display_name="数据隐私 / SaaS",
                description="SaaS、数据处理、个人信息处理和网络安全合同常用规则。",
                manifest_paths=(
                    "authorities/prc-data-security-law/effective-2021-09-01/manifest.json",
                    "authorities/prc-personal-information-protection-law/effective-2021-11-01/manifest.json",
                    "authorities/prc-cybersecurity-law/effective-2026-01-01/manifest.json",
                ),
                law_refs=("中华人民共和国个人信息保护法", "中华人民共和国数据安全法", "中华人民共和国网络安全法"),
                source_refs=OFFICIAL_SOURCES,
            ),
            PackDefinition(
                pack_id="cn-company-equity-financing-core",
                display_name="公司股权 / 投融资",
                description="股权转让、公司治理、投资协议和增资安排常用规则。",
                manifest_paths=("authorities/prc-company-law/effective-2024-07-01/manifest.json",),
                law_refs=("中华人民共和国公司法", "最高人民法院关于适用公司法若干问题的规定"),
                source_refs=OFFICIAL_SOURCES,
            ),
            PackDefinition(
                pack_id="cn-competition-commercial-core",
                display_name="竞争与商业合规",
                description="反不正当竞争、反垄断和商业合作中的竞争边界。",
                manifest_paths=(
                    "authorities/prc-anti-unfair-competition-law/effective-2025-10-15/manifest.json",
                    "authorities/prc-anti-monopoly-law/effective-2022-08-01/manifest.json",
                ),
                law_refs=("中华人民共和国反不正当竞争法", "中华人民共和国反垄断法"),
                source_refs=OFFICIAL_SOURCES,
            ),
        ),
    ),
    PackDefinition(
        pack_id="cn-intellectual-property-core",
        display_name="知识产权 / 技术许可",
        description="专利、商标、著作权和知识产权商业化合同常用规则。",
        law_refs=("中华人民共和国专利法", "中华人民共和国商标法", "中华人民共和国著作权法"),
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-service-outsourcing-core",
        display_name="服务 / 咨询 / 外包",
        description="服务交付、验收、费用、成果归属和外包管理常用规则。",
        law_refs=("中华人民共和国民法典", "最高人民法院关于适用民法典合同编通则若干问题的解释"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES + OPEN_SOURCE_REFERENCES,
    ),
    PackDefinition(
        pack_id="cn-software-development-core",
        display_name="软件开发",
        description="软件委托开发、交付验收、源代码、知识产权和维护服务规则。",
        law_refs=("中华人民共和国民法典", "中华人民共和国著作权法", "计算机软件保护条例"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES + OPEN_SOURCE_REFERENCES,
    ),
    PackDefinition(
        pack_id="cn-construction-core",
        display_name="建设工程",
        description="建设工程施工、分包、价款结算和工程质量争议常用规则。",
        manifest_paths=(
            "authorities/prc-civil-code-construction-contract-excerpt/effective-2021-01-01/manifest.json",
            "authorities/prc-construction-law/effective-2019-04-23/manifest.json",
            "authorities/state-council-construction-quality-regulation/effective-2019-04-23/manifest.json",
            "authorities/spc-construction-contract-interpretation-1/effective-2021-01-01/manifest.json",
        ),
        law_refs=(
            "中华人民共和国民法典（建设工程合同）",
            "中华人民共和国建筑法",
            "建设工程质量管理条例",
            "最高人民法院关于审理建设工程施工合同纠纷案件适用法律问题的解释（一）",
        ),
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-lease-property-core",
        display_name="房屋租赁 / 物业",
        description="房屋租赁、物业服务、场地使用和不动产相关合同规则。",
        law_refs=("中华人民共和国民法典（租赁合同）", "物业管理条例", "城镇房屋租赁合同司法解释"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-sale-supply-chain-core",
        display_name="买卖采购 / 供应链",
        description="买卖、采购、质量验收、交付、付款和违约责任规则。",
        law_refs=("中华人民共和国民法典（买卖合同）", "产品质量法", "招标投标法"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-logistics-transport-core",
        display_name="物流运输",
        description="运输、仓储、货损、延误和承运责任规则。",
        law_refs=("中华人民共和国民法典（运输合同、仓储合同）", "道路运输条例", "海商法"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-finance-loan-guarantee-core",
        display_name="金融借贷 / 担保",
        description="借款、担保、保证、抵押质押和融资安排常用规则。",
        law_refs=("中华人民共和国民法典（借款合同、保证合同）", "最高人民法院关于适用民法典担保制度的解释"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-consumer-ecommerce-core",
        display_name="消费者 / 电商",
        description="消费者权益、平台交易、网络销售和格式条款规则。",
        law_refs=("中华人民共和国消费者权益保护法", "中华人民共和国电子商务法", "网络交易监督管理办法"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-franchise-core",
        display_name="加盟 / 特许经营",
        description="商业特许经营、品牌授权、加盟费用和信息披露规则。",
        law_refs=("商业特许经营管理条例", "商业特许经营信息披露管理办法", "中华人民共和国商标法"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-advertising-marketing-core",
        display_name="广告营销 / 直播电商",
        description="广告发布、营销服务、主播合作和平台推广合规规则。",
        law_refs=("中华人民共和国广告法", "互联网广告管理办法", "网络直播营销管理办法"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-medical-health-core",
        display_name="医疗健康 / 药械",
        description="医疗服务、药品、医疗器械合作和健康数据规则。",
        law_refs=("中华人民共和国药品管理法", "医疗器械监督管理条例", "基本医疗卫生与健康促进法"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-education-training-core",
        display_name="教育培训",
        description="培训服务、退费、未成年人保护和校外培训监管规则。",
        law_refs=("中华人民共和国教育法", "中华人民共和国民办教育促进法", "校外培训行政处罚暂行办法"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-tender-government-procurement-core",
        display_name="招投标 / 政府采购",
        description="招投标、政府采购、履约保证和供应商责任规则。",
        law_refs=("中华人民共和国招标投标法", "中华人民共和国政府采购法", "招标投标法实施条例"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-cross-border-trade-core",
        display_name="涉外 / 跨境贸易",
        description="涉外买卖、国际贸易、海关和外汇相关合同规则。",
        law_refs=("中华人民共和国涉外民事关系法律适用法", "中华人民共和国对外贸易法", "中华人民共和国海关法"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-tax-invoice-core",
        display_name="税务 / 发票",
        description="价税、发票、代扣代缴和税务合规相关合同规则。",
        law_refs=("中华人民共和国税收征收管理法", "中华人民共和国发票管理办法", "增值税暂行条例"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-insurance-core",
        display_name="保险",
        description="保险合同、责任免除、理赔和保险中介规则。",
        law_refs=("中华人民共和国保险法", "保险销售行为管理办法"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-securities-fund-core",
        display_name="证券基金",
        description="证券、基金、私募投资和金融产品相关合同规则。",
        law_refs=("中华人民共和国证券法", "中华人民共和国证券投资基金法", "私募投资基金监督管理条例"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-environment-safety-core",
        display_name="环境 / 安全生产",
        description="环保责任、安全生产、危化品和施工安全相关合同规则。",
        law_refs=("中华人民共和国环境保护法", "中华人民共和国安全生产法", "危险化学品安全管理条例"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-platform-internet-service-core",
        display_name="平台规则 / 互联网服务",
        description="平台服务、用户协议、内容治理和网络服务责任规则。",
        law_refs=("中华人民共和国民法典", "中华人民共和国电子商务法", "互联网信息服务管理办法"),
        adapter_note=DEFAULT_ADAPTER_NOTE,
        source_refs=OFFICIAL_SOURCES,
    ),
)


_DOWNLOAD_TASKS: dict[UUID, LegalPackDownloadTask] = {}


def _load_manifest(path: Path) -> LegalManifest:
    return LegalManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _manifest_path(path_ref: str) -> Path:
    path = Path(path_ref)
    return path if path.is_absolute() else legal_data_root() / path


def _ready_pack_manifest_paths() -> dict[str, tuple[str, ...]]:
    try:
        discovered = discover_corpus_packs(legal_data_root())
    except (CorpusPackError, OSError):
        return {}
    return {
        pack.manifest.pack_id: tuple(member.authority_manifest_path for member in pack.members)
        for pack in discovered
        if pack.manifest.status.value == "READY"
    }


def _manifest_identities(relative_paths: tuple[str, ...]) -> set[tuple[str, str]]:
    identities: set[tuple[str, str]] = set()
    for relative in relative_paths:
        manifest_path = _manifest_path(relative)
        if not manifest_path.is_file():
            continue
        try:
            manifest = _load_manifest(manifest_path)
        except (OSError, ValueError):
            continue
        for record in manifest.records:
            identities.add((record.authority.authority_id, record.version_id))
    return identities


def _dedupe_paths(paths: list[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            out.append(path)
    return tuple(out)


def _bundled_manifest_paths_for_law_ref(law_ref: str) -> tuple[str, ...]:
    matches: list[str] = []
    root = legal_data_root()
    for keyword, paths in LOCAL_SNAPSHOT_HINTS.items():
        if keyword in law_ref:
            matches.extend(paths)
    return tuple(path for path in matches if (root / path).is_file())


def _normalize_law_ref(value: str) -> str:
    return (
        value.replace("（", "")
        .replace("）", "")
        .replace("(", "")
        .replace(")", "")
        .replace(" ", "")
        .strip()
    )


def _installed_law_ref_count(law_refs: tuple[str, ...], installed_titles: tuple[str, ...]) -> int:
    if not law_refs or not installed_titles:
        return 0
    normalized_titles = [_normalize_law_ref(title) for title in installed_titles]
    count = 0
    for law_ref in law_refs:
        normalized_ref = _normalize_law_ref(law_ref)
        if any(normalized_ref in title or title in normalized_ref for title in normalized_titles):
            count += 1
    return count


def _definition_manifest_resolution(
    definition: PackDefinition,
    ready_paths: dict[str, tuple[str, ...]],
) -> PackManifestResolution:
    if definition.manifest_paths:
        return PackManifestResolution(manifest_paths=definition.manifest_paths, unresolved_law_refs=())
    ready = ready_paths.get(definition.pack_id, ())
    if ready:
        return PackManifestResolution(manifest_paths=ready, unresolved_law_refs=())
    paths: list[str] = []
    unresolved: list[str] = []
    for law_ref in definition.law_refs:
        matched = _bundled_manifest_paths_for_law_ref(law_ref)
        if matched:
            paths.extend(matched)
        else:
            unresolved.append(law_ref)
    return PackManifestResolution(
        manifest_paths=_dedupe_paths(paths),
        unresolved_law_refs=tuple(unresolved),
    )


def _node(
    definition: PackDefinition,
    *,
    installed: set[tuple[str, str]],
    installed_titles: tuple[str, ...],
    ready_paths: dict[str, tuple[str, ...]],
) -> LegalPackTreeNode:
    resolution = _definition_manifest_resolution(definition, ready_paths)
    manifest_paths = resolution.manifest_paths
    identities = _manifest_identities(manifest_paths) if manifest_paths else set()
    if identities:
        installed_count = len(identities & installed)
    else:
        installed_count = _installed_law_ref_count(definition.law_refs, installed_titles)
    downloadable_refs = [law_ref for law_ref in resolution.unresolved_law_refs if has_official_text_source(law_ref)]
    authority_count = max(len(identities) + len(resolution.unresolved_law_refs), len(definition.law_refs))
    if identities and installed_count == len(identities) and not resolution.unresolved_law_refs:
        state: PackState = "INSTALLED"
    elif not identities and definition.law_refs and installed_count == len(definition.law_refs):
        state = "INSTALLED"
    elif identities or downloadable_refs:
        state = "AVAILABLE"
    else:
        state = "ADAPTER_PENDING"
    adapter_note = definition.adapter_note
    if resolution.unresolved_law_refs:
        pending_refs = [law_ref for law_ref in resolution.unresolved_law_refs if law_ref not in downloadable_refs]
        if downloadable_refs and pending_refs:
            ready = "、".join(downloadable_refs[:3])
            missing = "、".join(pending_refs[:3])
            adapter_note = f"{ready} 可从官方全文源下载；{missing} 的自动下载适配仍在补充。"
        elif downloadable_refs:
            ready = "、".join(downloadable_refs[:3])
            suffix = "等" if len(downloadable_refs) > 3 else ""
            adapter_note = f"{ready}{suffix} 可从官方全文源下载并自动入库。"
        else:
            missing = "、".join(resolution.unresolved_law_refs[:4])
            suffix = "等" if len(resolution.unresolved_law_refs) > 4 else ""
            adapter_note = f"可先安装已内置法源；{missing}{suffix} 的官方自动下载适配仍在补充。"
    return LegalPackTreeNode(
        pack_id=definition.pack_id,
        display_name=definition.display_name,
        description=definition.description,
        state=state,
        authority_count=authority_count,
        installed_authority_count=installed_count,
        law_refs=list(definition.law_refs),
        adapter_note=adapter_note if state in {"AVAILABLE", "ADAPTER_PENDING"} else None,
        source_refs=list(definition.source_refs),
        children=[
            _node(child, installed=installed, installed_titles=installed_titles, ready_paths=ready_paths)
            for child in definition.children
        ],
    )


def list_legal_pack_tree() -> list[LegalPackTreeNode]:
    ready_paths = _ready_pack_manifest_paths()
    db_path = legal_db_path()
    installed = list_version_identities(db_path)
    installed_titles = tuple(summary.authority.title for summary in list_authorities(db_path))
    return [
        _node(definition, installed=installed, installed_titles=installed_titles, ready_paths=ready_paths)
        for definition in PACK_TREE
    ]


def _find_definition(pack_id: str, definitions: tuple[PackDefinition, ...] = PACK_TREE) -> PackDefinition | None:
    for definition in definitions:
        if definition.pack_id == pack_id:
            return definition
        found = _find_definition(pack_id, definition.children)
        if found is not None:
            return found
    return None


def install_legal_pack(pack_id: str) -> LegalPackDownloadResponse:
    definition = _find_definition(pack_id)
    if definition is None:
        raise FileNotFoundError(f"Unknown legal pack: {pack_id}")

    ready_paths = _ready_pack_manifest_paths()
    resolution = _definition_manifest_resolution(definition, ready_paths)
    manifest_paths = list(resolution.manifest_paths)
    unresolved_after_download: list[str] = []
    online_enabled = os.getenv("LAW_RAG_LEGAL_ONLINE_DOWNLOADS", "1").strip().lower() not in {"0", "false", "no"}
    if resolution.unresolved_law_refs and online_enabled:
        download_root = runtime_dir() / "legal" / "official-downloads" / pack_id
        for law_ref in resolution.unresolved_law_refs:
            try:
                downloaded = download_npc_legal_manifest(law_ref, download_root)
                manifest_paths.append(str(downloaded.manifest_path))
            except OfficialLegalDownloadError as exc:
                message = str(exc)
                if "内网对象存储地址" in message or "无已适配的官方网页全文源" in message:
                    unresolved_after_download.append(f"{law_ref}（官方附件暂不可直连，需补充该法规网页全文源）")
                else:
                    unresolved_after_download.append(f"{law_ref}（{message.splitlines()[0][:80]}）")
    else:
        unresolved_after_download = list(resolution.unresolved_law_refs)
    if not manifest_paths:
        return LegalPackDownloadResponse(
            pack_id=pack_id,
            state="UNAVAILABLE",
            message=(
                "该领域暂无可安装的本机快照，且官方自动下载未启用或未成功；可先打开官方来源核验法规。"
            ),
            imported_records=0,
            no_change_records=0,
            rejected_records=0,
            rebuilt_index=False,
            summary=get_summary(legal_db_path()),
        )

    imported = 0
    no_change = 0
    rejected = 0
    db_path = legal_db_path()
    db_existed = db_path.exists()
    for index, relative in enumerate(manifest_paths):
        report = import_manifest(
            _manifest_path(relative),
            db_path,
            rebuild=(not db_existed and index == 0),
            source_registry_path=source_registry_path(),
            report_path=legal_last_import_report_path(),
        )
        imported += report.imported_records
        no_change += report.no_change_records
        rejected += report.rejected_records

    rebuilt_index = False
    index_path = legal_retrieval_index_path()
    index_needs_rebuild = imported > 0 or not index_path.exists()
    if not index_needs_rebuild:
        try:
            index_needs_rebuild = not get_retrieval_index_summary(index_path, db_path).ready
        except RetrievalIndexError:
            index_needs_rebuild = True
    if index_needs_rebuild:
        build_retrieval_index(db_path, index_path)
        rebuilt_index = True
    summary = get_summary(db_path)
    if unresolved_after_download:
        missing = "、".join(unresolved_after_download[:4])
        suffix = "等" if len(unresolved_after_download) > 4 else ""
        message = f"已安装/更新可用法源，并已处理索引；{missing}{suffix} 暂未成功自动下载。"
    else:
        message = "法律包已安装/更新，并已重建本地法律检索索引。"
    return LegalPackDownloadResponse(
        pack_id=pack_id,
        state="INSTALLED",
        message=message,
        imported_records=imported,
        no_change_records=no_change,
        rejected_records=rejected,
        rebuilt_index=rebuilt_index,
        summary=summary,
    )


def start_legal_pack_download(pack_id: str) -> LegalPackDownloadTask:
    task_id = uuid4()
    task = LegalPackDownloadTask(
        task_id=task_id,
        pack_id=pack_id,
        state="RUNNING",
        message="正在下载/安装领域法律包并重建索引。",
        progress_percent=10,
        started_at=datetime.now(timezone.utc),
    )
    _DOWNLOAD_TASKS[task_id] = task
    try:
        result = install_legal_pack(pack_id)
        task.state = "COMPLETE" if result.state == "INSTALLED" else "FAILED"
        task.progress_percent = 100
        task.message = result.message
        task.result = result
    except Exception as exc:
        task.state = "FAILED"
        task.progress_percent = 100
        task.message = str(exc)
    task.finished_at = datetime.now(timezone.utc)
    _DOWNLOAD_TASKS[task_id] = task
    return task


def get_legal_pack_download_task(task_id: UUID) -> LegalPackDownloadTask:
    task = _DOWNLOAD_TASKS.get(task_id)
    if task is None:
        raise FileNotFoundError(f"Unknown legal pack download task: {task_id}")
    return task
