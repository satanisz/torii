"""MLflow wrapper for a trusted AutoGluon predictor artifact."""

from __future__ import annotations

import mlflow.pyfunc
import pandas as pd
from autogluon.tabular import TabularPredictor


class AutoGluonPyFuncModel(mlflow.pyfunc.PythonModel):
    """Expose an AutoGluon predictor through MLflow's generic prediction API."""

    def load_context(self, context: mlflow.pyfunc.PythonModelContext) -> None:
        self.predictor = TabularPredictor.load(context.artifacts["predictor"])

    def predict(
        self,
        context: mlflow.pyfunc.PythonModelContext,
        model_input: pd.DataFrame,
        params: dict[str, object] | None = None,
    ) -> pd.DataFrame:
        predictions = self.predictor.predict(model_input)
        return pd.DataFrame({"prediction": predictions})
