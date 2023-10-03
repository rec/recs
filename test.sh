#!/bin/bash

set -eux

mypy recs
pytest
isort recs test
black recs test
ruff check --fix recs test
