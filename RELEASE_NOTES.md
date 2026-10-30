# Frequenz Client Marketmetering Library Release Notes

## Summary

<!-- Here goes a general summary of what this release is about -->

## Upgrading

<!-- Here goes notes on how to upgrade from previous versions, including deprecations and what they should be replaced with -->

- CLI: `list` always fetches every page, and its `--all-pages` option is
  removed. Drop `--all-pages` from any `marketmetering-cli list` invocation.

## New Features

<!-- Here goes the main new features and examples or instructions on how to use them -->

- CLI: `list --format csv` writes one row per Market Location to stdout, e.g.
  `marketmetering-cli list --activation ALL --format csv > malos.csv`.
- CLI: when neither an auth key nor a signing secret is given, both are read
  from `FREQUENZ_API_KEY` and `FREQUENZ_API_SECRET`. `MARKETMETERING_API_*` and
  the flags still take precedence, and the two are never mixed.

## Bug Fixes

<!-- Here goes notable bug fixes that are worth a special mention or explanation -->
