#!/usr/bin/env bash
set -e

uv sync

git config --local --unset-all core.hooksPath || true
pre-commit install --hook-type pre-commit --hook-type pre-push
