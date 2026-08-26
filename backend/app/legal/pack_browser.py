from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.storage import legal_db_path, legal_last_import_report_path, legal_retrieval_index_path

from .corpus_packs import discover_corpus_packs
from .importer import import_manifest
from .models import LegalManifest, LegalStoreSummary
from .retrieval import build_retrieval_index
from .store import get_summary, list_version_identities


REPO_ROOT = Path(__file__).resolve().parents[3]
LEGAL_DATA_ROOT = REPO_ROOT / "legal_data"
SOURCE_REGISTRY_PATH = LEGAL_DATA_ROOT / "source_registry.json"


PackState = Literal["INSTALLED", "AVAILABLE", "ADAPTER_PENDING"]
DownloadState = Literal["INSTALLED", "UNAVAILABLE"]


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


@dataclass(frozen=True)
class PackDefinition:
    pack_id: str
    display_name: str
    description: str
    manifest_paths: tuple[str, ...] = ()
    source_refs: tuple[LegalPackSource, ...] = ()
    children: tuple["PackDefinition", ...] = ()


OFFICIAL_SOURCES = (
    LegalPackSource(name="国家法律法规数据库", url="https://flk.npc.gov.cn/search"),
    LegalPackSource(name="司法部国家行政法规库", url="https://xzfg.moj.gov.cn/search2.html"),
    LegalPackSource(name="最高人民法院官网", url="https://www.court.gov.cn/"),
    LegalPackSource(name="最高人民法院公报", url="https://gongbao.court.gov.cn/"),
)


PACK_TREE: tuple[PackDefinition, ...] = (
    PackDefinition(
        pack_id="cn-contract-general-core",
        display_name="通用合同基础",
        description="民法典合同编核心条款与合同编通则司法解释选摘，作为所有合同审查的基础法源。",
        manifest_paths=("seed/manifest.json",),
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-labor-dispute-core",
        display_name="劳动用工",
        description="劳动合同、劳动争议、社会保险和相关司法解释。",
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-enterprise-compliance-core",
        display_name="企业合规与数据",
        description="公司治理、竞争合规、数据安全、个人信息保护和网络安全。",
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
                source_refs=OFFICIAL_SOURCES,
            ),
            PackDefinition(
                pack_id="cn-company-equity-financing-core",
                display_name="公司股权 / 投融资",
                description="股权转让、公司治理、投资协议和增资安排常用规则。",
                manifest_paths=("authorities/prc-company-law/effective-2024-07-01/manifest.json",),
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
                source_refs=OFFICIAL_SOURCES,
            ),
        ),
    ),
    PackDefinition(
        pack_id="cn-intellectual-property-core",
        display_name="知识产权 / 技术许可",
        description="专利、商标、著作权和知识产权商业化合同常用规则。",
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-construction-core",
        display_name="建设工程",
        description="建设工程施工、分包、价款结算和工程质量争议常用规则。",
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-lease-property-core",
        display_name="房屋租赁 / 物业",
        description="房屋租赁、物业服务、场地使用和不动产相关合同规则。",
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-sale-supply-chain-core",
        display_name="买卖采购 / 供应链",
        description="买卖、采购、质量验收、交付、付款和违约责任规则。",
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-logistics-transport-core",
        display_name="物流运输",
        description="运输、仓储、货损、延误和承运责任规则。",
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-finance-loan-guarantee-core",
        display_name="金融借贷 / 担保",
        description="借款、担保、保证、抵押质押和融资安排常用规则。",
        source_refs=OFFICIAL_SOURCES,
    ),
    PackDefinition(
        pack_id="cn-consumer-ecommerce-core",
        display_name="消费者 / 电商",
        description="消费者权益、平台交易、网络销售和格式条款规则。",
        source_refs=OFFICIAL_SOURCES,
    ),
)


def _load_manifest(path: Path) -> LegalManifest:
    return LegalManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _ready_pack_manifest_paths() -> dict[str, tuple[str, ...]]:
    discovered = discover_corpus_packs(LEGAL_DATA_ROOT)
    return {
        pack.manifest.pack_id: tuple(member.authority_manifest_path for member in pack.members)
        for pack in discovered
        if pack.manifest.status.value == "READY"
    }


def _manifest_identities(relative_paths: tuple[str, ...]) -> set[tuple[str, str]]:
    identities: set[tuple[str, str]] = set()
    for relative in relative_paths:
        manifest = _load_manifest(LEGAL_DATA_ROOT / relative)
        for record in manifest.records:
            identities.add((record.authority.authority_id, record.version_id))
    return identities


def _definition_manifest_paths(
    definition: PackDefinition,
    ready_paths: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    if definition.manifest_paths:
        return definition.manifest_paths
    return ready_paths.get(definition.pack_id, ())


def _node(
    definition: PackDefinition,
    *,
    installed: set[tuple[str, str]],
    ready_paths: dict[str, tuple[str, ...]],
) -> LegalPackTreeNode:
    manifest_paths = _definition_manifest_paths(definition, ready_paths)
    identities = _manifest_identities(manifest_paths) if manifest_paths else set()
    installed_count = len(identities & installed)
    if identities and installed_count == len(identities):
        state: PackState = "INSTALLED"
    elif identities:
        state = "AVAILABLE"
    else:
        state = "ADAPTER_PENDING"
    return LegalPackTreeNode(
        pack_id=definition.pack_id,
        display_name=definition.display_name,
        description=definition.description,
        state=state,
        authority_count=len(identities),
        installed_authority_count=installed_count,
        source_refs=list(definition.source_refs),
        children=[_node(child, installed=installed, ready_paths=ready_paths) for child in definition.children],
    )


def list_legal_pack_tree() -> list[LegalPackTreeNode]:
    ready_paths = _ready_pack_manifest_paths()
    installed = list_version_identities(legal_db_path())
    return [_node(definition, installed=installed, ready_paths=ready_paths) for definition in PACK_TREE]


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
    manifest_paths = _definition_manifest_paths(definition, ready_paths)
    if not manifest_paths:
        return LegalPackDownloadResponse(
            pack_id=pack_id,
            state="UNAVAILABLE",
            message="该领域的自动下载适配器尚未完成；可先打开官方来源核验法规。",
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
            LEGAL_DATA_ROOT / relative,
            db_path,
            rebuild=(not db_existed and index == 0),
            source_registry_path=SOURCE_REGISTRY_PATH if relative.startswith("authorities/") else None,
            report_path=legal_last_import_report_path(),
        )
        imported += report.imported_records
        no_change += report.no_change_records
        rejected += report.rejected_records

    build_retrieval_index(db_path, legal_retrieval_index_path())
    summary = get_summary(db_path)
    return LegalPackDownloadResponse(
        pack_id=pack_id,
        state="INSTALLED",
        message="法律包已安装/更新，并已重建本地法律检索索引。",
        imported_records=imported,
        no_change_records=no_change,
        rejected_records=rejected,
        rebuilt_index=True,
        summary=summary,
    )
