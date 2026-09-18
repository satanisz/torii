variable "REGISTRY" {
  default = "torii"
}

variable "IMAGE_NAME" {
  default = "workspace"
}

target "_base" {
  context    = "."
  dockerfile = "docker/Dockerfile"
}

target "py39-vanilla" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.9", PROFILE = "vanilla" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.9-vanilla"]
}

target "py39-ml-standard" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.9", PROFILE = "ml-standard" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.9-ml-standard"]
}

target "py39-ml-max" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.9", PROFILE = "ml-max" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.9-ml-max"]
}

target "py310-vanilla" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.10", PROFILE = "vanilla" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.10-vanilla"]
}

target "py310-ml-standard" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.10", PROFILE = "ml-standard" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.10-ml-standard"]
}

target "py310-ml-max" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.10", PROFILE = "ml-max" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.10-ml-max"]
}

target "py311-vanilla" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.11", PROFILE = "vanilla" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.11-vanilla"]
}

target "py311-ml-standard" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.11", PROFILE = "ml-standard" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.11-ml-standard"]
}

target "py311-ml-max" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.11", PROFILE = "ml-max" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.11-ml-max"]
}

target "py312-vanilla" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.12", PROFILE = "vanilla" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.12-vanilla"]
}

target "py312-ml-standard" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.12", PROFILE = "ml-standard" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.12-ml-standard"]
}

target "py312-ml-max" {
  inherits = ["_base"]
  args = { PYTHON_VERSION = "3.12", PROFILE = "ml-max" }
  tags = ["${REGISTRY}/${IMAGE_NAME}:py3.12-ml-max"]
}

group "default" {
  targets = [
    "py39-vanilla", "py39-ml-standard", "py39-ml-max",
    "py310-vanilla", "py310-ml-standard", "py310-ml-max",
    "py311-vanilla", "py311-ml-standard", "py311-ml-max",
    "py312-vanilla", "py312-ml-standard", "py312-ml-max"
  ]
}

group "vanilla" {
  targets = ["py39-vanilla", "py310-vanilla", "py311-vanilla", "py312-vanilla"]
}

group "ml-standard" {
  targets = ["py39-ml-standard", "py310-ml-standard", "py311-ml-standard", "py312-ml-standard"]
}

group "ml-max" {
  targets = ["py39-ml-max", "py310-ml-max", "py311-ml-max", "py312-ml-max"]
}
