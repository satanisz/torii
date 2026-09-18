#!/usr/bin/env bash
set -euo pipefail

image="${1:-torii/workspace:py3.12-ml-standard}"

docker run --rm \
  --env WORKSPACE_IDE=shell \
  "${image}" \
  bash -lc '
    python --version
    uv --version
    jupyter lab --version
    code-server --version
    test -f /workspace/.automl-scaffold-version
    python -c "import torii_project" 2>/dev/null || PYTHONPATH=/workspace/src python -c "import torii_project"
    case "${TORII_PROFILE}" in
      vanilla)
        ;;
      ml-standard)
        python -c "import torch, torchvision, xgboost; assert torch.version.cuda is None"
        ! uv pip list --format freeze | grep -qi "^nvidia-"
        ;;
      ml-max)
        python -c "import torch, torchaudio, torchvision, xgboost, pandas, sklearn, statsmodels, transformers, stable_baselines3, QuantLib, tables; assert torch.version.cuda is None"
        ! uv pip list --format freeze | grep -qi "^nvidia-"
        ;;
      automl-tabular)
        python -c "import autogluon, mlflow; from autogluon.tabular import TabularPredictor"
        ;;
      *)
        echo "Unknown TORII_PROFILE: ${TORII_PROFILE}" >&2
        exit 1
        ;;
    esac
  '
