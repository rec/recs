#!/bin/bash

set -eux

mypy recs
coverage run $(which pytest)
coverage html
isort recs test
black recs test
ruff check --fix recs test
