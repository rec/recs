#!/bin/bash

set -eux

mypy recs
isort recs test
black recs test
ruff check --fix recs test
coverage run $(which pytest)
coverage html
