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


async def test_credentials_fall_back_to_frequenz_env_vars(
    mocker: MockerFixture,
) -> None:
    """`FREQUENZ_API_*` are used when `MARKETMETERING_API_*` are unset."""
    client_cls = mocker.patch(
        "frequenz.client.marketmetering.__main__.MarketMeteringApiClient"
    )
    client_cls.return_value.list_market_locations = AsyncMock(return_value=([], None))

    result = await CliRunner().invoke(
        cli,
        ["--url", "grpc://x", "list"],
        env={
            "MARKETMETERING_API_AUTH_KEY": None,
            "MARKETMETERING_API_SIGN_SECRET": None,
            "FREQUENZ_API_KEY": "fallback-key",
            "FREQUENZ_API_SECRET": "fallback-secret",
        },
    )

    assert result.exit_code == 0, result.output
    assert client_cls.call_args.kwargs["auth_key"] == "fallback-key"
    assert client_cls.call_args.kwargs["sign_secret"] == "fallback-secret"


async def test_marketmetering_env_vars_take_precedence(
    mocker: MockerFixture,
) -> None:
    """`MARKETMETERING_API_*` win over `FREQUENZ_API_*`."""
    client_cls = mocker.patch(
        "frequenz.client.marketmetering.__main__.MarketMeteringApiClient"
    )
    client_cls.return_value.list_market_locations = AsyncMock(return_value=([], None))

    result = await CliRunner().invoke(
        cli,
        ["--url", "grpc://x", "list"],
        env={
            "MARKETMETERING_API_AUTH_KEY": "own-key",
            "MARKETMETERING_API_SIGN_SECRET": "own-secret",
            "FREQUENZ_API_KEY": "fallback-key",
            "FREQUENZ_API_SECRET": "fallback-secret",
        },
    )

    assert result.exit_code == 0, result.output
    assert client_cls.call_args.kwargs["auth_key"] == "own-key"
    assert client_cls.call_args.kwargs["sign_secret"] == "own-secret"


async def test_credentials_are_not_mixed_across_sources(
    mocker: MockerFixture,
) -> None:
    """A `MARKETMETERING_API_*` key is never paired with a `FREQUENZ_API_*` secret."""
    client_cls = mocker.patch(
        "frequenz.client.marketmetering.__main__.MarketMeteringApiClient"
    )
    client_cls.return_value.list_market_locations = AsyncMock(return_value=([], None))

    result = await CliRunner().invoke(
        cli,
        ["--url", "grpc://x", "list"],
        env={
            "MARKETMETERING_API_AUTH_KEY": "own-key",
            "MARKETMETERING_API_SIGN_SECRET": None,
            "FREQUENZ_API_KEY": "fallback-key",
            "FREQUENZ_API_SECRET": "fallback-secret",
        },
    )

    assert result.exit_code == 0, result.output
    assert client_cls.call_args.kwargs["auth_key"] == "own-key"
    assert client_cls.call_args.kwargs["sign_secret"] is None


async def test_secret_without_key_does_not_fall_back(
    mocker: MockerFixture,
) -> None:
    """A `MARKETMETERING_API_*` secret alone is an error, not a mixed pair."""
    client_cls = mocker.patch(
        "frequenz.client.marketmetering.__main__.MarketMeteringApiClient"
    )

    result = await CliRunner().invoke(
        cli,
        ["--url", "grpc://x", "list"],
        env={
            "MARKETMETERING_API_AUTH_KEY": None,
            "MARKETMETERING_API_SIGN_SECRET": "own-secret",
            "FREQUENZ_API_KEY": "fallback-key",
            "FREQUENZ_API_SECRET": "fallback-secret",
        },
    )

    assert result.exit_code != 0
    assert "auth key" in result.output
    client_cls.assert_not_called()
