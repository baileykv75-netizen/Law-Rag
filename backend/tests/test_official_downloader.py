from __future__ import annotations

import json

import httpx

from app.legal.models import CoverageType
from app.legal.official_downloader import download_npc_legal_manifest, has_official_text_source


def test_npc_downloader_builds_import_manifest_from_official_api_payload(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://flk.npc.gov.cn/law-search/search/list":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "rows": [
                        {
                            "bbbs": "npc-ad-law-001",
                            "title": "中华人民共和国广告法",
                        }
                    ],
                },
            )
        if str(request.url) == "https://flk.npc.gov.cn/law-search/search/flfgDetails?bbbs=npc-ad-law-001":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "bbbs": "npc-ad-law-001",
                        "title": "中华人民共和国广告法",
                        "office": "全国人民代表大会常务委员会",
                        "f_wenhao": "中华人民共和国主席令第二十二号",
                        "gbrq": "2015-04-24",
                        "sxrq": "2015-09-01",
                        "content": """
                        <html><body>
                        <p>中华人民共和国广告法</p>
                        <p>第一条 为了规范广告活动，保护消费者的合法权益，制定本法。</p>
                        <p>第二条 在中华人民共和国境内，商品经营者或者服务提供者通过一定媒介和形式直接或者间接地介绍自己所推销的商品或者服务的商业广告活动，适用本法。</p>
                        </body></html>
                        """,
                    }
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        downloaded = download_npc_legal_manifest("中华人民共和国广告法", tmp_path, client=client)

    manifest = json.loads(downloaded.manifest_path.read_text(encoding="utf-8"))
    record = manifest["records"][0]
    assert downloaded.article_count == 2
    assert record["authority"]["title"] == "中华人民共和国广告法"
    assert record["authority"]["authority_type"] == "LAW"
    assert record["version_id"] == "effective-2015-09-01"
    assert record["coverage_type"] == CoverageType.FULL_TEXT.value
    assert record["expected_article_count"] == 2
    assert record["source_refs"][0]["url"].startswith("https://flk.npc.gov.cn/detail")


def test_npc_downloader_uses_official_html_text_source_when_detail_has_no_body(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://flk.npc.gov.cn/law-search/search/list":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "rows": [
                        {
                            "bbbs": "npc-ad-law-2021",
                            "title": "<em class='highlight'>中华人民共和国</em><em class='highlight'>广告法</em>",
                            "gbrq": "2021-04-29",
                            "sxrq": "2021-04-29",
                            "sxx": 3,
                        }
                    ],
                },
            )
        if url == "https://flk.npc.gov.cn/law-search/search/flfgDetails?bbbs=npc-ad-law-2021":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "bbbs": "npc-ad-law-2021",
                        "title": "中华人民共和国广告法",
                        "zdjgName": "全国人民代表大会常务委员会",
                        "gbrq": "2021-04-29",
                        "sxrq": "2021-04-29",
                        "sxx": 3,
                        "content": {"title": "中华人民共和国广告法", "children": []},
                        "ossFile": {},
                    },
                },
            )
        if url == "https://www.gov.cn/guoqing/2021-10/29/content_5647620.htm":
            return httpx.Response(
                200,
                text="""
                <html><body>
                  <div class="pages_content">
                    <p>中华人民共和国广告法</p>
                    <p>第一条 为了规范广告活动，保护消费者的合法权益，制定本法。</p>
                    <p>第二条 在中华人民共和国境内，商业广告活动适用本法。</p>
                    <p>第三条 广告应当真实、合法。</p>
                  </div>
                </body></html>
                """,
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        downloaded = download_npc_legal_manifest("中华人民共和国广告法", tmp_path, client=client)

    manifest = json.loads(downloaded.manifest_path.read_text(encoding="utf-8"))
    record = manifest["records"][0]
    assert downloaded.article_count == 3
    assert record["authority"]["title"] == "中华人民共和国广告法"
    assert record["authority"]["issuing_body"] == "全国人民代表大会常务委员会"
    assert record["source_refs"][1]["name"].startswith("中国政府网")
    assert record["source_refs"][1]["url"] == "https://www.gov.cn/guoqing/2021-10/29/content_5647620.htm"


def test_known_official_html_sources_are_marked_downloadable() -> None:
    assert has_official_text_source("中华人民共和国广告法")
    assert not has_official_text_source("暂未适配法规")
