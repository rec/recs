#!/bin/bash

set -eux

mypy recs
pytest
isort recs test
black recs
ruff check --fix recs
