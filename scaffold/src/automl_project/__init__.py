"""Compatibility namespace for existing AutoML notebooks and model artifacts.

New code should import torii_project. Searching that package's path keeps old
automl_project submodule imports loadable without copying the implementation.
"""

from torii_project import __path__ as __path__
