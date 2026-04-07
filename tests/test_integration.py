# License: MIT
# Copyright © 2026 Frequenz Energy-as-a-Service GmbH

"""Integration tests for the MarketMeteringApiClient against a live service.

These tests use testcontainers to spin up GreptimeDB and run the
marketmeteringd service binary. They require:
1. Docker to be running
2. The marketmeteringd binary to be built (run 'cargo build --release' in the service repo)
3. The service repo to be checked out at ../frequenz-service-marketmetering

To run: uv run pytest -m integration
"""

import grpc
import pytest
from grpc.aio import AioRpcError

from frequenz.client.marketmetering import MarketMeteringApiClient
from frequenz.client.marketmetering.types import (
    EnergyFlowDirection,
    MarketArea,
    MarketLocation,
    MarketLocationId,
    MarketLocationIdType,
    MarketLocationRef,
    MarketLocationUpdate,
    MetricType,
    TimeResolution,
)


def make_ref(
    enterprise_id: int = 42, malo_id: str = "DE0000000001"
) -> MarketLocationRef:
    """Create a MarketLocationRef for testing."""
    return MarketLocationRef(
        enterprise_id=enterprise_id,
        market_area=MarketArea.EU_DE,
        market_location_id=MarketLocationId(
            value=malo_id,
            type=MarketLocationIdType.MALO_ID,
        ),
    )


def make_location(
    display_name: str = "Test Location",
    directions: list[EnergyFlowDirection] | None = None,
    time_resolution: TimeResolution = TimeResolution.MIN_15,
) -> MarketLocation:
    """Create a MarketLocation for testing."""
    if directions is None:
        directions = [EnergyFlowDirection.IMPORT]
    return MarketLocation(
        display_name=display_name,
        supported_directions=directions,
        time_resolution=time_resolution,
        payload={},
    )


class TestCreateMarketLocation:
    """Tests for create_market_location."""

    async def test_create_basic(self, client: MarketMeteringApiClient) -> None:
        """Test creating a basic market location."""
        ml_ref = make_ref(enterprise_id=1, malo_id="DE_CREATE_BASIC_001")
        ml = make_location(display_name="Basic Test")

        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

    async def test_create_with_both_directions(
        self, client: MarketMeteringApiClient
    ) -> None:
        """Test creating a market location with import and export."""
        ml_ref = make_ref(enterprise_id=1, malo_id="DE_CREATE_BOTH_DIR_001")
        ml = make_location(
            display_name="Both Directions",
            directions=[EnergyFlowDirection.IMPORT, EnergyFlowDirection.EXPORT],
        )

        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

    async def test_create_with_payload(self, client: MarketMeteringApiClient) -> None:
        """Test creating a market location with payload metadata."""
        ml_ref = make_ref(enterprise_id=1, malo_id="DE_CREATE_PAYLOAD_001")
        ml = MarketLocation(
            display_name="With Payload",
            supported_directions=[EnergyFlowDirection.IMPORT],
            time_resolution=TimeResolution.MIN_15,
            payload={"meter_serial": "ABC123", "location_type": "industrial"},
        )

        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

    async def test_create_duplicate_fails(
        self, client: MarketMeteringApiClient
    ) -> None:
        """Test that creating a duplicate market location fails."""
        ml_ref = make_ref(enterprise_id=1, malo_id="DE_CREATE_DUP_001")
        ml = make_location(display_name="First")

        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

        with pytest.raises(AioRpcError) as exc_info:
            await client.create_market_location(
                market_location_ref=ml_ref,
                market_location=ml,
            )
        assert exc_info.value.code() == grpc.StatusCode.ALREADY_EXISTS

    async def test_create_with_different_resolutions(
        self, client: MarketMeteringApiClient
    ) -> None:
        """Test creating locations with various time resolutions."""
        for i, res in enumerate(
            [
                TimeResolution.MIN_1,
                TimeResolution.MIN_5,
                TimeResolution.MIN_15,
                TimeResolution.MIN_60,
                TimeResolution.DAY_1,
            ]
        ):
            ml_ref = make_ref(enterprise_id=1, malo_id=f"DE_CREATE_RES_{i:03d}")
            ml = make_location(
                display_name=f"Resolution {res.name}",
                time_resolution=res,
            )
            await client.create_market_location(
                market_location_ref=ml_ref,
                market_location=ml,
            )


class TestUpdateMarketLocation:
    """Tests for update_market_location."""

    async def test_update_display_name(self, client: MarketMeteringApiClient) -> None:
        """Test updating the display name of a market location."""
        ml_ref = make_ref(enterprise_id=2, malo_id="DE_UPDATE_NAME_001")
        ml = make_location(display_name="Original Name")

        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

        update = MarketLocationUpdate(display_name="Updated Name")
        await client.update_market_location(
            market_location_ref=ml_ref,
            update=update,
            expected_revision=1,
        )

    async def test_update_supported_directions(
        self, client: MarketMeteringApiClient
    ) -> None:
        """Test adding a direction to supported_directions."""
        ml_ref = make_ref(enterprise_id=2, malo_id="DE_UPDATE_DIR_001")
        ml = make_location(
            display_name="Direction Update",
            directions=[EnergyFlowDirection.IMPORT],
        )

        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

        update = MarketLocationUpdate(
            supported_directions=[
                EnergyFlowDirection.IMPORT,
                EnergyFlowDirection.EXPORT,
            ],
        )
        await client.update_market_location(
            market_location_ref=ml_ref,
            update=update,
            expected_revision=1,
        )

    async def test_update_time_resolution_to_finer(
        self, client: MarketMeteringApiClient
    ) -> None:
        """Test changing time_resolution to a finer resolution."""
        ml_ref = make_ref(enterprise_id=2, malo_id="DE_UPDATE_RES_001")
        ml = make_location(
            display_name="Resolution Update",
            time_resolution=TimeResolution.MIN_15,
        )

        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

        update = MarketLocationUpdate(time_resolution=TimeResolution.MIN_5)
        await client.update_market_location(
            market_location_ref=ml_ref,
            update=update,
            expected_revision=1,
        )

    async def test_update_time_resolution_to_coarser(
        self, client: MarketMeteringApiClient
    ) -> None:
        """Test that changing to a coarser resolution succeeds."""
        ml_ref = make_ref(enterprise_id=2, malo_id="DE_UPDATE_RES_COARSE_001")
        ml = make_location(
            display_name="Coarser OK",
            time_resolution=TimeResolution.MIN_15,
        )

        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

        update = MarketLocationUpdate(time_resolution=TimeResolution.MIN_60)
        await client.update_market_location(
            market_location_ref=ml_ref,
            update=update,
            expected_revision=1,
        )

    async def test_update_payload(self, client: MarketMeteringApiClient) -> None:
        """Test updating the payload."""
        ml_ref = make_ref(enterprise_id=2, malo_id="DE_UPDATE_PAY_001")
        ml = make_location(display_name="Payload Update")

        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

        update = MarketLocationUpdate(payload={"new_key": "new_value"})
        await client.update_market_location(
            market_location_ref=ml_ref,
            update=update,
            expected_revision=1,
        )

    async def test_update_nonexistent_fails(
        self, client: MarketMeteringApiClient
    ) -> None:
        """Test that updating a non-existent location fails."""
        ml_ref = make_ref(enterprise_id=2, malo_id="DE_NONEXISTENT_001")
        update = MarketLocationUpdate(display_name="Ghost")

        with pytest.raises(AioRpcError):
            await client.update_market_location(
                market_location_ref=ml_ref,
                update=update,
                expected_revision=1,
            )

    async def test_sequential_updates_increment_revision(
        self, client: MarketMeteringApiClient
    ) -> None:
        """Test that sequential updates require incrementing revision."""
        ml_ref = make_ref(enterprise_id=2, malo_id="DE_UPDATE_SEQ_001")
        ml = make_location(display_name="Sequential")

        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

        await client.update_market_location(
            market_location_ref=ml_ref,
            update=MarketLocationUpdate(display_name="Updated Once"),
            expected_revision=1,
        )

        await client.update_market_location(
            market_location_ref=ml_ref,
            update=MarketLocationUpdate(display_name="Updated Twice"),
            expected_revision=2,
        )

        # Stale revision should fail
        with pytest.raises(AioRpcError) as exc_info:
            await client.update_market_location(
                market_location_ref=ml_ref,
                update=MarketLocationUpdate(display_name="Stale"),
                expected_revision=1,
            )
        assert "conflict" in (exc_info.value.details() or "").lower()


class TestListMarketLocations:
    """Tests for list_market_locations."""

    async def test_list_returns_results(self, client: MarketMeteringApiClient) -> None:
        """Test that list_market_locations returns results."""
        # Create a location first so there's something to list.
        ml_ref = make_ref(enterprise_id=3, malo_id="DE_LIST_001")
        ml = make_location(display_name="Listable")
        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

        entries, _ = await client.list_market_locations(enterprise_id=3)
        assert len(entries) >= 1


class TestActivateDeactivate:
    """Tests for activate/deactivate market locations."""

    async def test_deactivate_and_activate(
        self, client: MarketMeteringApiClient
    ) -> None:
        """Test deactivating and reactivating a market location."""
        ml_ref = make_ref(enterprise_id=3, malo_id="DE_ACT_DEACT_001")
        ml = make_location(display_name="Toggle Active")
        await client.create_market_location(
            market_location_ref=ml_ref,
            market_location=ml,
        )

        results = await client.deactivate_market_locations(
            market_location_refs=[ml_ref]
        )
        assert len(results) == 1
        assert results[0].error is None

        results = await client.activate_market_locations(market_location_refs=[ml_ref])
        assert len(results) == 1
        assert results[0].error is None


class TestStreamSamples:
    """Tests for stream_samples."""

    async def test_stream_returns_no_error(
        self, client: MarketMeteringApiClient
    ) -> None:
        """Test that stream_samples can be called without error."""
        ml_ref = make_ref(enterprise_id=3, malo_id="DE_STREAM_001")
        async for _ in client.stream_samples(
            market_locations=[ml_ref],
            directions=[EnergyFlowDirection.IMPORT],
            metric_types=[MetricType.ACTIVE_ENERGY],
        ):
            break  # Just verify the stream starts without error
