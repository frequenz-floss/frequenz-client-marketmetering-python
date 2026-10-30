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

## Bug Fixes

<!-- Here goes notable bug fixes that are worth a special mention or explanation -->
