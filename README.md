# Frequenz Market Metering Client

[![Build Status](https://github.com/frequenz-floss/frequenz-client-marketmetering-python/actions/workflows/ci.yaml/badge.svg)](https://github.com/frequenz-floss/frequenz-client-marketmetering-python/actions/workflows/ci.yaml)
[![PyPI Package](https://img.shields.io/pypi/v/frequenz-client-marketmetering)](https://pypi.org/project/frequenz-client-marketmetering/)
[![Docs](https://img.shields.io/badge/docs-latest-informational)](https://frequenz-floss.github.io/frequenz-client-marketmetering-python/)

## Introduction

A Python client for the Frequenz Market Metering API, providing access to
historical and real-time metering samples from Market Locations across various
energy markets (Germany, UK, US, Australia, etc.).

## Features

- Stream metering samples from Market Locations
- Support for multiple market identifier types (MaLo-ID, MPAN, ESI-ID, NMI)
- Filtering by energy flow direction (import/export)
- Multiple metric types (active energy, active power, reactive energy/power)
- Optional resampling for time-series aggregation
- CLI tool for quick access to metering data

## Installation

```bash
pip install frequenz-client-marketmetering
```

For CLI support:

```bash
pip install "frequenz-client-marketmetering[cli]"
```

## Quick Start

### Python API

```python
from datetime import datetime, timezone
from frequenz.client.marketmetering import MarketMeteringApiClient
from frequenz.client.marketmetering.types import (
    EnergyFlowDirection,
    MarketArea,
    MarketLocationId,
    MarketLocationIdType,
    MarketLocationRef,
    MetricType,
)

# Create client
client = MarketMeteringApiClient(
    server_url="grpc://marketmetering.example.com",
    auth_key="your-api-key",
)

# Define a Market Location (e.g., German MaLo)
market_location = MarketLocationRef(
    market_area=MarketArea.EU_DE,
    market_location_id=MarketLocationId(
        value="DE01234567890",
        type=MarketLocationIdType.MALO_ID,
    ),
)

# Stream metering samples
async for series in client.stream_samples(
    market_locations=[market_location],
    directions=[EnergyFlowDirection.IMPORT],
    metric_types=[MetricType.ACTIVE_ENERGY],
    start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
):
    for sample in series.samples:
        print(f"{sample.sample_time}: {sample.value} {series.metric_unit.name}")
```

### CLI

```bash
# Set environment variables
export MARKETMETERING_API_URL="grpc://marketmetering.example.com"
export MARKETMETERING_API_AUTH_KEY="your-api-key"
export MARKETMETERING_API_SIGN_SECRET="your-secret"  # optional
# If neither is set, FREQUENZ_API_KEY and FREQUENZ_API_SECRET are used as a pair.

# Stream samples from a German Market Location
marketmetering-cli stream EU_DE:DE01234567890:MALO_ID

# Stream with specific options
marketmetering-cli stream EU_DE:DE01234567890:MALO_ID \
    --direction IMPORT \
    --metric ACTIVE_ENERGY \
    --start-time "2025-01-01T00:00:00" \
    --resolution MIN_15
```

## Market Location Types

The client supports various market identifier types:

| Type | Market | Example |
|------|--------|---------|
| `MALO_ID` | Germany | `DE01234567890` |
| `MPAN` | United Kingdom | `18106612345678901234` |
| `ESI_ID` | US (ERCOT) | `10443720000012345` |
| `NMI` | Australia | `NEM1203456A` |

## Supported Platforms

- **Python:** 3.11+
- **Operating System:** Ubuntu Linux 20.04+
- **Architectures:** amd64, arm64

## Documentation

For detailed documentation, please visit:
https://frequenz-floss.github.io/frequenz-client-marketmetering-python/

## Contributing

If you want to know how to build this project and contribute to it, please
check out the [Contributing Guide](CONTRIBUTING.md).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file
for details.
