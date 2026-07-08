#!/usr/bin/env bash
set -euxo pipefail

part="${1:-patch}"

if [[ "$part" != "patch" && "$part" != "minor" && "$part" != "major" ]]; then
  echo "usage: scripts/release.sh [patch|minor|major]" >&2
  exit 2
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "release requires a clean working tree" >&2
  exit 1
fi

branch="$(git branch --show-current)"
if [[ "$branch" != "main" ]]; then
  echo "release must run from main, not $branch" >&2
  exit 1
fi

target_version="$(uv version --bump "$part" --dry-run --short)"
tag="v$target_version"

if git rev-parse --verify --quiet "$tag" >/dev/null; then
  echo "tag already exists: $tag" >&2
  exit 1
fi

if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null; then
  echo "remote tag already exists: $tag" >&2
  exit 1
fi

uv run pytest
uv run ruff check --fix --select B,E,F,I recs install test*
uv run ruff format --check recs install test*
uv run ty check recs
python_version="$(cat .python-version)"
python_version="${python_version//./}"
find install test recs -name '*.py' | xargs uv run pyupgrade --py"${python_version}"-plus
git diff --check

if [[ -n "$(git status --porcelain)" ]]; then
  echo "release verification changed the working tree" >&2
  exit 1
fi

build_root="${TMPDIR:-/tmp}/recs-release-build"
repo_root="$(pwd)"
uv run --with pyinstaller --with pillow pyinstaller \
  --noconfirm \
  --distpath "$build_root/dist" \
  --workpath "$build_root/build" \
  --specpath "$build_root" \
  --windowed \
  --disable-windowed-traceback \
  --name Recs \
  --hidden-import recs.ui.gui_child \
  --hidden-import _sounddevice \
  --hidden-import _soundfile \
  --collect-binaries _sounddevice_data \
  --collect-binaries _soundfile_data \
  --add-data "$repo_root/recs:recs" \
  --add-data "$repo_root/README.md:README.md" \
  --add-data "$repo_root/packaging/README-WINDOWS.txt:README-WINDOWS.txt" \
  --add-data "$repo_root/packaging/README-MACOS.txt:README-MACOS.txt" \
  --add-data "$repo_root/packaging/README-LINUX.txt:README-LINUX.txt" \
  install/pyinstaller_entrypoint.py

if [[ "$(uname)" == "Darwin" ]]; then
  codesign --force --deep --sign - "$build_root/dist/Recs.app"
fi

uv version --bump "$part" --no-sync
version="$(uv version --short)"
tag="v$version"

if [[ "$version" != "$target_version" ]]; then
  echo "version changed after dry run: expected $target_version, got $version" >&2
  exit 1
fi

git add pyproject.toml uv.lock
git commit -m "Release $tag"
git push
git tag "$tag"
git push origin "$tag"
