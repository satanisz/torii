# %%
# Run this file in VS Code's Python Interactive window or copy the cells into a
# Jupyter notebook. The model and all experiment metadata are written to MLflow,
# not to the notebook process.
from torii_project.automl import run_demo
from torii_project.automl.demo import REGISTERED_MODEL_NAME

# %%
result = run_demo(time_limit=120, preset="medium_quality")
result  # noqa: B018 - displayed by Jupyter/VS Code Interactive

# %%
# This works in a new notebook or workspace as long as MLFLOW_TRACKING_URI is set.
import mlflow.pyfunc
import pandas as pd

model = mlflow.pyfunc.load_model(
    f"models:/{REGISTERED_MODEL_NAME}@candidate"
)
raw_data = pd.read_csv("data/raw/breast_cancer.csv")
model.predict(raw_data.drop(columns=["malignant"]).head(3))
