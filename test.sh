#!/bin/bash

set -eux

black recs
ruff check --fix recs
mypy recs
pytest
