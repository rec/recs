#!/bin/bash

set -eux

isort recs test
black recs
ruff check --fix recs
mypy recs
pytest
