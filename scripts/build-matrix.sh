#!/usr/bin/env bash
set -euo pipefail

python_version="${PYTHON_VERSION:-3.12}"
profile="${PROFILE:-ml-standard}"
image_repository="${IMAGE_REPOSITORY:-torii/workspace}"

if [[ "${1:-}" == "--all" ]]; then
  python_versions=(3.9 3.10 3.11 3.12)
  profiles=(vanilla ml-standard ml-max)
else
  python_versions=("${python_version}")
  profiles=("${profile}")
fi

for python in "${python_versions[@]}"; do
  for selected_profile in "${profiles[@]}"; do
    tag="${image_repository}:py${python}-${selected_profile}"
    docker build \
      --file docker/Dockerfile \
      --build-arg "PYTHON_VERSION=${python}" \
      --build-arg "PROFILE=${selected_profile}" \
      --tag "${tag}" \
      .
  done
done
