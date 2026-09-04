# License: MIT
# Copyright © 2025 Frequenz Energy-as-a-Service GmbH

"""CLI for the Market Metering client."""

import asyncio
import os
import shlex
from datetime import datetime, timezone
from pprint import pformat
from typing import Any

import asyncclick as click
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import NestedCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import CompleteStyle

from ._client import MarketMeteringApiClient
from .types import (
    ActivationFilter,
    EnergyFlowDirection,
    MarketArea,
    MarketLocation,
    MarketLocationDetail,
    MarketLocationId,
    MarketLocationIdType,
    MarketLocationOperationResult,
    MarketLocationRef,
    MarketLocationSeries,
    MarketLocationsFilter,
    MarketLocationUpdate,
    MetricType,
    ResamplingOptions,
    TimeResolution,
)


def format_datetime(dt: datetime | None) -> str:
    """Format datetime object to a readable string, or return 'N/A' if None."""
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z") if dt else "N/A"


def print_series(series: MarketLocationSeries, raw: bool = False) -> None:
    """Print the series details in a nicely formatted way with colors."""
    if raw:
        click.echo(pformat(series, compact=True))
        return

    # Header
    click.echo(click.style("Market Location Series:", bold=True, underline=True))

    # Market Location info
    ml_ref = series.market_location_ref
    click.echo(f"  {click.style('Enterprise ID:', fg='cyan')} {ml_ref.enterprise_id}")
    click.echo(
        f"  {click.style('Location ID:', fg='cyan')} "
        f"{ml_ref.market_location_id.value} ({ml_ref.market_location_id.type.name})"
    )
    click.echo(f"  {click.style('Direction:', fg='cyan')} {series.direction.name}")
    click.echo(
        f"  {click.style('Metric:', fg='cyan')} "
        f"{series.metric_type.name} [{series.metric_unit.name}]"
    )
    click.echo(f"  {click.style('Resolution:', fg='cyan')} {series.resolution.name}")

    # Samples
    click.echo(
        f"\n  {click.style('Samples:', fg='green')} ({len(series.samples)} total)"
    )
    for sample in series.samples[:10]:  # Limit display to first 10
        value_str = f"{sample.value:.4f}" if sample.value is not None else "N/A"
        quality_color = "green" if sample.quality.name == "MEASURED" else "yellow"
        click.echo(
            f"    {format_datetime(sample.sample_time)}: "
            f"{click.style(value_str, fg='white')} "
            f"[{click.style(sample.quality.name, fg=quality_color)}]"
        )

    if len(series.samples) > 10:
        click.echo(f"    ... and {len(series.samples) - 10} more samples")

    click.echo()


def print_detail(detail: MarketLocationDetail, raw: bool = False) -> None:
    """Print a MarketLocationDetail in a nicely formatted way."""
    if raw:
        click.echo(pformat(detail, compact=True))
        return

    click.echo(click.style("Market Location:", bold=True, underline=True))
    ref = detail.market_location_ref
    click.echo(f"  {click.style('Enterprise ID:', fg='cyan')} {ref.enterprise_id}")
    click.echo(
        f"  {click.style('Location ID:', fg='cyan')} "
        f"{ref.market_location_id.value} ({ref.market_location_id.type.name})"
    )

    ml = detail.market_location
    click.echo(f"  {click.style('Display Name:', fg='cyan')} {ml.display_name}")
    click.echo(f"  {click.style('Market Area:', fg='cyan')} {ref.market_area.name}")
    click.echo(
        f"  {click.style('Directions:', fg='cyan')} "
        f"{', '.join(d.name for d in ml.supported_directions)}"
    )
    click.echo(f"  {click.style('Resolution:', fg='cyan')} {ml.time_resolution.name}")
    if ml.payload:
        click.echo(f"  {click.style('Payload:', fg='cyan')} {ml.payload}")

    status_color = "green" if detail.is_active else "red"
    click.echo(
        f"  {click.style('Active:', fg='cyan')} "
        f"{click.style(str(detail.is_active), fg=status_color)}"
    )
    click.echo(f"  {click.style('Revision:', fg='cyan')} {detail.revision}")
    click.echo(
        f"  {click.style('Created:', fg='cyan')} {format_datetime(detail.create_time)}"
    )
    click.echo(
        f"  {click.style('Updated:', fg='cyan')} {format_datetime(detail.update_time)}"
    )
    if detail.last_deactivated_time:
        click.echo(
            f"  {click.style('Last Deactivated:', fg='cyan')} "
            f"{format_datetime(detail.last_deactivated_time)}"
        )
    click.echo()


def print_operation_result(
    result: MarketLocationOperationResult, raw: bool = False
) -> None:
    """Print an activate/deactivate operation result."""
    if raw:
        click.echo(pformat(result, compact=True))
        return

    ref = result.market_location_ref
    loc_str = (
        f"{ref.enterprise_id}:{ref.market_location_id.value}"
        f":{ref.market_location_id.type.name}"
    )
    if result.error is None:
        click.echo(
            f"  {click.style('OK', fg='green')} {loc_str} (rev {result.revision})"
        )
    else:
        click.echo(
            f"  {click.style('FAIL', fg='red')} {loc_str}: "
            f"{result.error.code.name} - {result.error.message}"
        )


@click.group(invoke_without_command=True)
@click.option(
    "--url",
    help="Market Metering API URL",
    envvar="MARKETMETERING_API_URL",
    show_envvar=True,
)
@click.option(
    "--auth-key",
    help="API auth key for authentication",
    envvar="MARKETMETERING_API_AUTH_KEY",
    show_envvar=True,
    required=False,
)
@click.option(
    "--sign-secret",
    help="API signing secret for authentication",
    envvar="MARKETMETERING_API_SIGN_SECRET",
    show_envvar=True,
    required=False,
    default=None,
)
@click.option(
    "--raw",
    is_flag=True,
    help="Print output raw instead of formatted and colored",
    required=False,
    default=False,
)
@click.pass_context
async def cli(
    ctx: click.Context,
    url: str,
    auth_key: str | None,
    sign_secret: str | None,
    raw: bool,
) -> None:
    """Market Metering Service CLI."""
    if ctx.obj is None:
        ctx.obj = {}

    if not auth_key:
        raise click.BadParameter(
            "You must provide an API auth key using --auth-key or "
            "the MARKETMETERING_API_AUTH_KEY environment variable."
        )

    click.echo(f"Using API URL: {url}", err=True)
    click.echo(f"Using API Auth Key: {auth_key[:4]}{'*' * 8}", err=True)

    if sign_secret:
        if len(sign_secret) > 8:
            click.echo(
                f"Using API Signing Secret: {sign_secret[:4]}{'*' * 8}", err=True
            )
        else:
            click.echo("Using API Signing Secret (not shown).", err=True)

    ctx.obj["client"] = MarketMeteringApiClient(
        server_url=url,
        auth_key=auth_key,
        sign_secret=sign_secret,
        connect=True,
    )

    ctx.obj["params"] = {
        "url": url,
        "auth_key": auth_key,
        "sign_secret": sign_secret,
    }

    ctx.obj["raw"] = raw

    # Check if a subcommand was given
    if ctx.invoked_subcommand is None:
        await interactive_mode(url, auth_key, sign_secret)


def parse_market_location(value: str) -> MarketLocationRef:
    """Parse a market location string.

    Format: market_area:location_id:type
    Example: EU_DE:DE01234567890:MALO_ID
    """
    parts = value.split(":")
    if len(parts) != 3:
        raise click.BadParameter(
            f"Invalid market location format: {value}. "
            "Expected format: market_area:location_id:type"
        )

    try:
        market_area = MarketArea[parts[0].upper()]
    except KeyError as exc:
        valid_areas = ", ".join(a.name for a in MarketArea if a.name != "UNSPECIFIED")
        raise click.BadParameter(
            f"Invalid market area: {parts[0]}. Valid areas: {valid_areas}"
        ) from exc

    location_id = parts[1]

    try:
        id_type = MarketLocationIdType[parts[2].upper()]
    except KeyError as exc:
        valid_types = ", ".join(
            t.name for t in MarketLocationIdType if t.name != "UNSPECIFIED"
        )
        raise click.BadParameter(
            f"Invalid location type: {parts[2]}. Valid types: {valid_types}"
        ) from exc

    return MarketLocationRef(
        market_area=market_area,
        market_location_id=MarketLocationId(value=location_id, type=id_type),
    )


class MarketLocationParamType(click.ParamType[MarketLocationRef]):
    """Click parameter type for market locations."""

    name = "market_location"

    def convert(
        self, value: Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> MarketLocationRef:
        """Convert the value to a MarketLocationRef."""
        if isinstance(value, MarketLocationRef):
            return value
        try:
            return parse_market_location(str(value))
        except click.BadParameter as e:
            self.fail(str(e), param, ctx)


@cli.command("stream")
@click.pass_context
@click.argument(
    "market-locations",
    required=True,
    type=MarketLocationParamType(),
    nargs=-1,
)
@click.option(
    "--direction",
    "-d",
    type=click.Choice([d.name for d in EnergyFlowDirection if d.name != "UNSPECIFIED"]),
    multiple=True,
    default=["IMPORT"],
    help="Energy flow direction(s)",
)
@click.option(
    "--metric",
    "-m",
    type=click.Choice([m.name for m in MetricType if m.name != "UNSPECIFIED"]),
    multiple=True,
    default=["ACTIVE_ENERGY"],
    help="Metric type(s)",
)
@click.option(
    "--start-time",
    type=click.DateTime(),
    help="Start time for historical data (ISO format)",
)
@click.option(
    "--end-time",
    type=click.DateTime(),
    help="End time (ISO format). If omitted, streams in real-time.",
)
@click.option(
    "--resolution",
    type=click.Choice([r.name for r in TimeResolution if r.name != "UNSPECIFIED"]),
    help="Resampling resolution",
)
# pylint: disable=too-many-arguments,too-many-positional-arguments
async def stream_cmd(
    ctx: click.Context,
    market_locations: tuple[MarketLocationRef, ...],
    direction: tuple[str, ...],
    metric: tuple[str, ...],
    start_time: datetime | None,
    end_time: datetime | None,
    resolution: str | None,
) -> None:
    """Stream metering samples from Market Locations.

    MARKET_LOCATIONS are specified as: market_area:location_id:type

    Example:
        EU_DE:DE01234567890:MALO_ID

    Valid types: MALO_ID, MPAN, ESI_ID, NMI, OTHER

    Args:
        ctx: Click context with client and options.
        market_locations: Market location references to stream.
        direction: Energy flow directions (IMPORT/EXPORT).
        metric: Metric types to request.
        start_time: Optional start time for historical data.
        end_time: Optional end time.
        resolution: Optional resampling resolution.
    """
    client: MarketMeteringApiClient = ctx.obj["client"]
    raw: bool = ctx.obj["raw"]

    directions = [EnergyFlowDirection[d] for d in direction]
    metric_types = [MetricType[m] for m in metric]

    # Make times timezone-aware if provided
    if start_time and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time and end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    resampling = None
    if resolution:
        resampling = ResamplingOptions(resolution=TimeResolution[resolution])

    click.echo(
        f"Streaming from {len(market_locations)} market location(s)...", err=True
    )

    try:
        async for series in client.stream_samples(
            market_locations=list(market_locations),
            directions=directions,
            metric_types=metric_types,
            start_time=start_time,
            end_time=end_time,
            resampling=resampling,
        ):
            print_series(series, raw=raw)
    except KeyboardInterrupt:
        click.echo("\nStream interrupted.", err=True)


@cli.command("create")
@click.pass_context
@click.argument(
    "market-location",
    required=True,
    type=MarketLocationParamType(),
)
@click.option(
    "--name",
    required=True,
    help="Display name for the Market Location",
)
@click.option(
    "--direction",
    "-d",
    type=click.Choice([d.name for d in EnergyFlowDirection if d.name != "UNSPECIFIED"]),
    multiple=True,
    required=True,
    help="Supported energy flow direction(s)",
)
@click.option(
    "--resolution",
    type=click.Choice([r.name for r in TimeResolution if r.name != "UNSPECIFIED"]),
    default="MIN_15",
    help="Time resolution (default: MIN_15)",
)
# pylint: disable=too-many-arguments,too-many-positional-arguments
async def create_cmd(
    ctx: click.Context,
    market_location: MarketLocationRef,
    name: str,
    direction: tuple[str, ...],
    resolution: str,
) -> None:
    """Create a new Market Location.

    MARKET_LOCATION is specified as: market_area:location_id:type

    Example:
        create EU_DE:50601159037:MALO_ID --name "My Location" -d IMPORT

    Args:
        ctx: Click context with client and options.
        market_location: Market location reference.
        name: Display name for the location.
        direction: Supported energy flow directions.
        resolution: Time resolution for metering data.
    """
    client: MarketMeteringApiClient = ctx.obj["client"]
    raw: bool = ctx.obj["raw"]

    ml = MarketLocation(
        display_name=name,
        supported_directions=[EnergyFlowDirection[d] for d in direction],
        time_resolution=TimeResolution[resolution],
        payload={},
    )

    detail = await client.create_market_location(
        market_location_ref=market_location,
        market_location=ml,
    )
    click.echo(click.style("Created successfully.", fg="green"), err=True)
    print_detail(detail, raw=raw)


@cli.command("list")
@click.pass_context
@click.option(
    "--activation",
    type=click.Choice([a.name for a in ActivationFilter if a.name != "UNSPECIFIED"]),
    default="ONLY_ACTIVE",
    help="Activation filter (default: ONLY_ACTIVE)",
)
@click.option(
    "--all-pages",
    is_flag=True,
    default=False,
    help="Fetch all pages (default: first page only)",
)
async def list_cmd(
    ctx: click.Context,
    activation: str,
    all_pages: bool,
) -> None:
    """List Market Locations for the authenticated enterprise.

    Example:
        list

        list --activation ALL

    Args:
        ctx: Click context with client and options.
        activation: Activation status filter.
        all_pages: Whether to fetch all pages.
    """
    client: MarketMeteringApiClient = ctx.obj["client"]
    raw: bool = ctx.obj["raw"]

    filters = MarketLocationsFilter(
        activation_filter=ActivationFilter[activation],
    )

    total = 0
    next_page = None
    while True:
        entries, next_page = await client.list_market_locations(
            filters=filters,
            pagination_params=next_page,
        )
        for entry in entries:
            print_detail(entry.market_location_detail, raw=raw)
            total += 1

        if not all_pages or next_page is None:
            break

    click.echo(f"Total: {total} location(s)", err=True)


@cli.command("activate")
@click.pass_context
@click.argument(
    "market-locations",
    required=True,
    type=MarketLocationParamType(),
    nargs=-1,
)
async def activate_cmd(
    ctx: click.Context,
    market_locations: tuple[MarketLocationRef, ...],
) -> None:
    """Activate one or more Market Locations.

    MARKET_LOCATIONS are specified as: market_area:location_id:type

    Example:
        activate EU_DE:50601159037:MALO_ID

    Args:
        ctx: Click context with client and options.
        market_locations: Market location references to activate.
    """
    client: MarketMeteringApiClient = ctx.obj["client"]
    raw: bool = ctx.obj["raw"]

    results = await client.activate_market_locations(
        market_location_refs=list(market_locations),
    )
    for result in results:
        print_operation_result(result, raw=raw)


@cli.command("deactivate")
@click.pass_context
@click.argument(
    "market-locations",
    required=True,
    type=MarketLocationParamType(),
    nargs=-1,
)
async def deactivate_cmd(
    ctx: click.Context,
    market_locations: tuple[MarketLocationRef, ...],
) -> None:
    """Deactivate one or more Market Locations.

    MARKET_LOCATIONS are specified as: market_area:location_id:type

    Example:
        deactivate EU_DE:50601159037:MALO_ID

    Args:
        ctx: Click context with client and options.
        market_locations: Market location references to deactivate.
    """
    client: MarketMeteringApiClient = ctx.obj["client"]
    raw: bool = ctx.obj["raw"]

    results = await client.deactivate_market_locations(
        market_location_refs=list(market_locations),
    )
    for result in results:
        print_operation_result(result, raw=raw)


@cli.command("update")
@click.pass_context
@click.argument(
    "market-location",
    required=True,
    type=MarketLocationParamType(),
)
@click.option("--revision", required=True, type=int, help="Expected current revision")
@click.option("--name", default=None, help="New display name")
@click.option(
    "--direction",
    "-d",
    type=click.Choice([d.name for d in EnergyFlowDirection if d.name != "UNSPECIFIED"]),
    multiple=True,
    default=None,
    help="New supported direction(s) (replaces existing)",
)
@click.option(
    "--resolution",
    type=click.Choice([r.name for r in TimeResolution if r.name != "UNSPECIFIED"]),
    default=None,
    help="New time resolution",
)
# pylint: disable=too-many-arguments,too-many-positional-arguments
async def update_cmd(
    ctx: click.Context,
    market_location: MarketLocationRef,
    revision: int,
    name: str | None,
    direction: tuple[str, ...],
    resolution: str | None,
) -> None:
    """Update a Market Location.

    Requires the current revision number (use 'list' to find it).

    Example:
        update EU_DE:50601159037:MALO_ID --revision 3 --name "New Name"

    Args:
        ctx: Click context with client and options.
        market_location: Market location reference to update.
        revision: Expected current revision for optimistic concurrency.
        name: New display name (optional).
        direction: New supported directions (optional, replaces existing).
        resolution: New time resolution (optional).

    Raises:
        click.UsageError: If no fields to update are provided.
    """
    client: MarketMeteringApiClient = ctx.obj["client"]
    raw: bool = ctx.obj["raw"]

    directions = [EnergyFlowDirection[d] for d in direction] if direction else None
    time_res = TimeResolution[resolution] if resolution else None

    if not any([name, directions, time_res]):
        raise click.UsageError("At least one field to update must be provided.")

    update = MarketLocationUpdate(
        display_name=name,
        supported_directions=directions,
        time_resolution=time_res,
    )

    detail = await client.update_market_location(
        market_location_ref=market_location,
        update=update,
        expected_revision=revision,
    )
    click.echo(click.style("Updated successfully.", fg="green"), err=True)
    print_detail(detail, raw=raw)


@cli.command()
@click.pass_obj
async def repl(obj: dict[str, Any]) -> None:
    """Start an interactive interface."""
    await interactive_mode(
        obj["params"]["url"],
        obj["params"]["auth_key"],
        obj["params"]["sign_secret"],
    )


async def interactive_mode(url: str, auth_key: str, sign_secret: str | None) -> None:
    """Interactive mode for the CLI."""
    hist_file = os.path.expanduser("~/.marketmetering_cli_history.txt")
    session: PromptSession[str] = PromptSession(history=FileHistory(filename=hist_file))

    user_commands = [
        "create",
        "list",
        "stream",
        "activate",
        "deactivate",
        "update",
        "exit",
        "help",
    ]

    async def display_help() -> None:
        await cli.main(args=["--help"], standalone_mode=False)

    completer = NestedCompleter.from_nested_dict(
        {command: None for command in user_commands}
    )

    while True:
        with patch_stdout():
            try:
                user_input = await session.prompt_async(
                    "> ",
                    completer=completer,
                    complete_style=CompleteStyle.READLINE_LIKE,
                )
            except EOFError:
                break

        if user_input == "help" or not user_input:
            await display_help()
        elif user_input == "exit":
            break
        else:
            params = (
                ["--url", url, "--auth-key", auth_key]
                + (["--sign-secret", sign_secret] if sign_secret else [])
                + shlex.split(user_input)
            )

            try:
                await cli.main(args=params, standalone_mode=False)
            except click.ClickException as e:
                click.echo(e)


def main() -> None:
    """Entrypoint for the CLI."""
    asyncio.run(cli.main())


if __name__ == "__main__":
    main()
