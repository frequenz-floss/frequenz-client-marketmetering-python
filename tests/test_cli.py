# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Tests for the Market Metering CLI."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from asyncclick.testing import CliRunner
from pytest_mock import MockerFixture

from frequenz.client.marketmetering.__main__ import CSV_FIELDS, cli
from frequenz.client.marketmetering.types import (
    EnergyFlowDirection,
    MarketArea,
    MarketLocation,
    MarketLocationDetail,
    MarketLocationEntry,
    MarketLocationId,
    MarketLocationIdType,
    MarketLocationRef,
    PaginationParams,
    TimeResolution,
)

_TIME = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _entry(location_id: str, is_active: bool = True) -> MarketLocationEntry:
    return MarketLocationEntry(
        enterprise_id=7,
        market_location_detail=MarketLocationDetail(
            market_location_ref=MarketLocationRef(
                market_area=MarketArea.EU_DE,
                market_location_id=MarketLocationId(
                    value=location_id, type=MarketLocationIdType.MALO_ID
                ),
            ),
            market_location=MarketLocation(
                display_name=f"name {location_id}",
                supported_directions=[
                    EnergyFlowDirection.IMPORT,
                    EnergyFlowDirection.EXPORT,
                ],
                time_resolution=TimeResolution.MIN_15,
                payload={},
            ),
            revision=2,
            is_active=is_active,
            create_time=_TIME,
            update_time=_TIME,
            last_deactivated_time=None,
        ),
    )


def _two_page_client(mocker: MockerFixture) -> MagicMock:
    client = MagicMock()
    client.list_market_locations = AsyncMock(
        side_effect=[
            ([_entry("111")], PaginationParams(page_token="next")),
            ([_entry("222", is_active=False)], None),
        ]
    )
    mocker.patch(
        "frequenz.client.marketmetering.__main__.MarketMeteringApiClient",
        return_value=client,
    )
    return client


async def test_list_fetches_all_pages(mocker: MockerFixture) -> None:
    """`list` follows pagination to the last page."""
    client = _two_page_client(mocker)

    result = await CliRunner().invoke(
        cli, ["--url", "grpc://x", "--auth-key", "key", "list"]
    )

    assert result.exit_code == 0, result.output
    assert client.list_market_locations.await_count == 2
    assert "111" in result.stdout and "222" in result.stdout


async def test_list_csv(mocker: MockerFixture) -> None:
    """`--format csv` writes a header and one row per Market Location."""
    _two_page_client(mocker)

    result = await CliRunner().invoke(
        cli,
        ["--url", "grpc://x", "--auth-key", "key", "list", "--format", "csv"],
    )

    assert result.exit_code == 0, result.output
    assert "\r" not in result.stdout
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    assert list(rows[0]) == CSV_FIELDS
    assert [r["location_id"] for r in rows] == ["111", "222"]
    assert rows[0] == {
        "enterprise_id": "7",
        "market_area": "EU_DE",
        "location_id": "111",
        "id_type": "MALO_ID",
        "display_name": "name 111",
        "directions": "IMPORT;EXPORT",
        "time_resolution": "MIN_15",
        "is_active": "True",
        "revision": "2",
        "create_time": "2026-01-02T03:04:05+00:00",
        "update_time": "2026-01-02T03:04:05+00:00",
        "last_deactivated_time": "",
    }
    assert rows[1]["is_active"] == "False"
