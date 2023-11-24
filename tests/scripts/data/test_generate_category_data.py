"""Test generate category data."""
from base64 import b64encode
import json
from unittest.mock import ANY, patch

from aiohttp import ClientSession
from aresponses import ResponsesMockServer
from homeassistant.core import HomeAssistant
import pytest

from scripts.data.generate_category_data import OUTPUT_DIR, generate_category_data

from tests.common import (
    MockedResponse,
    ProxyClientSession,
    ResponseMocker,
    client_session_proxy,
    recursive_remove_key,
    safe_json_dumps,
)
from tests.conftest import SnapshotFixture
from tests.sample_data import integration_manifest, repository_data, tree_files_base

BASE_HEADERS = {"Content-Type": "application/json"}
RATE_LIMIT_HEADER = {
    **BASE_HEADERS,
    "X-RateLimit-Limit": "9999",
    "X-RateLimit-Remaining": "9999",
    "X-RateLimit-Reset": "9999",
}


@pytest.mark.asyncio
async def test_generate_category_data(
    aresponses: ResponsesMockServer,
):
    """Test behaviour."""
    repositories = [
        {"full_name": "test/first", "id": 999999998},
        {"full_name": "test/second", "id": 999999999},
    ]
    current_data = {
        f"{repositories[0]['id']}": {
            "manifest": {"name": "test"},
            "description": "Old contents",
            "full_name": repositories[0]["full_name"],
            "last_commit": "123",
            "etag_repository": "231",
            "stargazers_count": 992,
            "topics": [],
        }
    }
    aresponses.add(
        "api.github.com",
        "/rate_limit",
        "get",
        aresponses.Response(
            body=json.dumps({"resources": {"core": {"remaining": 9999}}}), headers=BASE_HEADERS
        ),
    )
    aresponses.add(
        "data-v2.hacs.xyz",
        "/removed/repositories.json",
        "get",
        aresponses.Response(
            body=json.dumps([]),
            headers=BASE_HEADERS,
        ),
    )

    aresponses.add(
        "data-v2.hacs.xyz",
        "/template/data.json",
        "get",
        aresponses.Response(
            body=json.dumps(current_data),
            headers=BASE_HEADERS,
        ),
    )

    aresponses.add(
        "api.github.com",
        "/repos/hacs/default/contents/template",
        "get",
        aresponses.Response(
            body=json.dumps(
                {
                    "content": b64encode(
                        json.dumps([x["full_name"] for x in repositories]).encode("utf-8")
                    ).decode("utf-8")
                }
            ),
            headers=BASE_HEADERS,
        ),
    )

    for repo in repositories:
        aresponses.add(
            "api.github.com",
            f"/repos/{repo['full_name']}",
            "get",
            aresponses.Response(
                body=json.dumps(
                    {
                        **repository_data,
                        "id": repo["id"],
                        "full_name": repo["full_name"],
                    }
                ),
                headers=BASE_HEADERS,
            ),
        )

        aresponses.add(
            "api.github.com",
            f"/repos/{repo['full_name']}/branches/main",
            "get",
            aresponses.Response(
                body=json.dumps({"commit": {"sha": "1234567890123456789012345678901234567890"}}),
                headers=BASE_HEADERS,
            ),
        )
        aresponses.add(
            "api.github.com",
            f"/repos/{repo['full_name']}/git/trees/main",
            "get",
            aresponses.Response(
                body=json.dumps(
                    {
                        "tree": [
                            *tree_files_base["tree"],
                            {"path": "test.jinja", "type": "blob"},
                        ]
                    }
                ),
                headers=BASE_HEADERS,
            ),
        )

        aresponses.add(
            "api.github.com",
            f"/repos/{repo['full_name']}/branches/main",
            "get",
            aresponses.Response(
                body=json.dumps({"commit": {"sha": "1234567890123456789012345678901234567890"}}),
                headers=BASE_HEADERS,
            ),
        )
        aresponses.add(
            "api.github.com",
            f"/repos/{repo['full_name']}/releases",
            "get",
            aresponses.Response(
                body=json.dumps([]),
                headers=BASE_HEADERS,
            ),
        )
        aresponses.add(
            "api.github.com",
            f"/repos/{repo['full_name']}/contents/hacs.json",
            "get",
            aresponses.Response(
                body=json.dumps(
                    {
                        "content": b64encode(
                            json.dumps({"name": "test", "filename": "test.jinja"}).encode("utf-8")
                        ).decode("utf-8")
                    }
                ),
                headers=BASE_HEADERS,
            ),
        )

        aresponses.add(
            "api.github.com",
            f"/repos/{repo['full_name']}/contents/readme.md",
            "get",
            aresponses.Response(
                body=json.dumps({"content": b64encode(b"").decode("utf-8")}),
                headers=BASE_HEADERS,
            ),
        )
        aresponses.add(
            "api.github.com",
            "/rate_limit",
            "get",
            aresponses.Response(
                body=json.dumps({"resources": {"core": {"remaining": 9999}}}), headers=BASE_HEADERS
            ),
        )

    await generate_category_data("template")

    with open(f"{OUTPUT_DIR}/template/data.json", encoding="utf-8") as file:
        data = json.loads(file.read())
        assert data == {
            "999999998": {
                "manifest": {"name": "test"},
                "description": "Sample description for repository.",
                "full_name": "test/first",
                "last_commit": "1234567",
                "stargazers_count": 999,
                "topics": ["topic1", "topic2"],
                "last_fetched": ANY,
            },
            "999999999": {
                "manifest": {"name": "test"},
                "description": "Sample description for repository.",
                "full_name": "test/second",
                "last_commit": "1234567",
                "stargazers_count": 999,
                "topics": ["topic1", "topic2"],
                "last_fetched": ANY,
            },
        }

    with open(f"{OUTPUT_DIR}/template/repositories.json", encoding="utf-8") as file:
        data = json.loads(file.read())
        assert "test/first" in data
        assert "test/second" in data
        assert len(data) == 2


@pytest.mark.asyncio
async def test_generate_category_data_single_repository(
    hass: HomeAssistant,
    response_mocker: ResponseMocker,
    snapshots: SnapshotFixture,
):
    """Test behaviour if single repository."""
    response_mocker.add(
        "https://data-v2.hacs.xyz/integration/data.json", MockedResponse(content={})
    )
    with patch("scripts.data.generate_category_data.ClientSession", ProxyClientSession):
        await generate_category_data("integration", "hacs-test-org/integration-basic")

    with open(f"{OUTPUT_DIR}/integration/data.json", encoding="utf-8") as file:
        snapshots.assert_match(
            safe_json_dumps(recursive_remove_key(json.loads(file.read()), ("last_fetched",))),
            "scripts/data/generate_category_data/single/data.json",
        )

    with open(f"{OUTPUT_DIR}/integration/repositories.json", encoding="utf-8") as file:
        snapshots.assert_match(
            safe_json_dumps(json.loads(file.read())),
            "scripts/data/generate_category_data/single/repositories.json",
        )
