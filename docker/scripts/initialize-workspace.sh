#!/usr/bin/env bash
set -euo pipefail

workspace_dir="${1:-${WORKSPACE_DIR:-/workspace}}"
scaffold_dir="${SCAFFOLD_DIR:-/opt/torii/scaffold}"
marker="${workspace_dir}/.automl-scaffold-version"
in_progress="${workspace_dir}/.automl-scaffold-in-progress"
scaffold_version="${SCAFFOLD_VERSION:-1}"

# Modern GNU cp supports --update=none; Git Bash's older coreutils use -n.
# Both variants preserve existing files, including user-edited source code.
copy_options=(-a -n)
if cp --help | grep -q -- '--update\[=UPDATE\]'; then
  copy_options=(-a --update=none)
fi

mkdir -p "${workspace_dir}"

# Recognize the earlier FrameML scaffold without changing its marker or files.
if [[ ! -e "${marker}" && -f "${workspace_dir}/.frameml-scaffold-version" ]]; then
  echo "Adding Torii scaffold files to an existing FrameML workspace."
  cp "${copy_options[@]}" "${scaffold_dir}/." "${workspace_dir}/"
  printf '%s\n' "${scaffold_version}" > "${marker}"
  exit 0
fi

if [[ -e "${marker}" ]] && [[ "$(<"${marker}")" == "${scaffold_version}" ]]; then
  exit 0
elif [[ -e "${marker}" ]]; then
  echo "Adding new Torii scaffold files for version ${scaffold_version}; existing files are preserved."
  cp "${copy_options[@]}" "${scaffold_dir}/." "${workspace_dir}/"
  printf '%s\n' "${scaffold_version}" > "${marker}"
  exit 0
fi

if [[ -e "${in_progress}" ]]; then
  echo "Resuming interrupted Torii scaffold initialization in ${workspace_dir}."
elif find "${workspace_dir}" -mindepth 1 -maxdepth 1 ! -name lost+found -print -quit | grep -q .; then
  echo "Workspace is not empty; existing content is preserved and scaffold creation is skipped."
  exit 0
else
  : > "${in_progress}"
  echo "Creating Torii project scaffold in ${workspace_dir}."
fi

cp "${copy_options[@]}" "${scaffold_dir}/." "${workspace_dir}/"

for required_path in README.md pyproject.toml src notebooks; do
  if [[ ! -e "${workspace_dir}/${required_path}" ]]; then
    echo "Scaffold initialization failed: missing ${required_path}." >&2
    exit 70
  fi
done

printf '%s\n' "${scaffold_version}" > "${marker}"
rm -f "${in_progress}"
