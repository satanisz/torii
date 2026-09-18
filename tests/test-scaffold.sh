#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
initializer="${root_dir}/docker/scripts/initialize-workspace.sh"
scaffold="${root_dir}/scaffold"
test_root="$(mktemp -d)"
trap 'rm -rf "${test_root}"' EXIT

empty_workspace="${test_root}/empty"
SCAFFOLD_DIR="${scaffold}" "${initializer}" "${empty_workspace}"
test -f "${empty_workspace}/README.md"
test -f "${empty_workspace}/.gitignore"
test -f "${empty_workspace}/.automl-scaffold-version"
test -f "${empty_workspace}/src/torii_project/config.py"
test -f "${empty_workspace}/src/automl_project/__init__.py"

printf 'owned by user\n' > "${empty_workspace}/README.md"
SCAFFOLD_DIR="${scaffold}" "${initializer}" "${empty_workspace}"
grep -q 'owned by user' "${empty_workspace}/README.md"

migration_scaffold="${test_root}/migration-scaffold"
cp -a "${scaffold}" "${migration_scaffold}"
printf 'new in version 2\n' > "${migration_scaffold}/new-mvp-file.txt"
SCAFFOLD_DIR="${migration_scaffold}" SCAFFOLD_VERSION=2 "${initializer}" "${empty_workspace}"
grep -q 'owned by user' "${empty_workspace}/README.md"
grep -q 'new in version 2' "${empty_workspace}/new-mvp-file.txt"
grep -q '^2$' "${empty_workspace}/.automl-scaffold-version"

# A previously initialized AutoML workspace gains Torii modules on upgrade,
# while existing project metadata and user code remain untouched.
legacy_workspace="${test_root}/legacy"
mkdir -p "${legacy_workspace}/src/automl_project"
printf '2\n' > "${legacy_workspace}/.automl-scaffold-version"
printf 'user model\n' > "${legacy_workspace}/src/automl_project/custom.py"
printf 'user project\n' > "${legacy_workspace}/pyproject.toml"
SCAFFOLD_DIR="${scaffold}" SCAFFOLD_VERSION=3 "${initializer}" "${legacy_workspace}"
test -f "${legacy_workspace}/src/torii_project/config.py"
grep -q 'user model' "${legacy_workspace}/src/automl_project/custom.py"
grep -q 'user project' "${legacy_workspace}/pyproject.toml"
grep -q '^3$' "${legacy_workspace}/.automl-scaffold-version"

frameml_workspace="${test_root}/frameml"
mkdir -p "${frameml_workspace}/src/frameml_project"
printf '2\n' > "${frameml_workspace}/.frameml-scaffold-version"
printf 'existing FrameML model\n' > "${frameml_workspace}/src/frameml_project/model.py"
SCAFFOLD_DIR="${scaffold}" SCAFFOLD_VERSION=3 "${initializer}" "${frameml_workspace}"
test -f "${frameml_workspace}/src/torii_project/config.py"
grep -q 'existing FrameML model' "${frameml_workspace}/src/frameml_project/model.py"
grep -q '^2$' "${frameml_workspace}/.frameml-scaffold-version"
grep -q '^3$' "${frameml_workspace}/.automl-scaffold-version"

nonempty_workspace="${test_root}/nonempty"
mkdir -p "${nonempty_workspace}"
printf 'keep me\n' > "${nonempty_workspace}/existing.txt"
SCAFFOLD_DIR="${scaffold}" "${initializer}" "${nonempty_workspace}"
test -f "${nonempty_workspace}/existing.txt"
test ! -e "${nonempty_workspace}/README.md"

resumed_workspace="${test_root}/resumed"
mkdir -p "${resumed_workspace}"
touch "${resumed_workspace}/.automl-scaffold-in-progress"
SCAFFOLD_DIR="${scaffold}" "${initializer}" "${resumed_workspace}"
test -f "${resumed_workspace}/README.md"
test ! -e "${resumed_workspace}/.automl-scaffold-in-progress"

echo "Scaffold tests passed."
