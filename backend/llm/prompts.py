"""Prompt versioning loader.

Loads versioned prompt files from the prompts/ directory.
Each agent role (tutor, evaluator, learner, analyst) has its own subdirectory.
"""

import os
from typing import Dict, Optional

from .config import PROJECT_ROOT, prompt_version_default

PROMPTS_ROOT = os.path.join(PROJECT_ROOT, "prompts")


def _read_prompt(role: str, version: str) -> str:
    path = os.path.join(PROMPTS_ROOT, role, f"{role}_{version}.txt")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Prompt not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def load_tutor_prompt(version: Optional[str] = None) -> str:
    """Load the tutor prompt. Defaults to the configured prompt_version."""
    return _read_prompt("tutor", version or prompt_version_default())


def load_evaluator_prompt(version: Optional[str] = None) -> str:
    """Load the evaluator prompt. Defaults to the configured prompt_version."""
    return _read_prompt("evaluator", version or prompt_version_default())


def load_learner_prompt(version: Optional[str] = None) -> str:
    """Load the learner (simulated) prompt. Defaults to the configured prompt_version."""
    return _read_prompt("learner", version or prompt_version_default())


def load_analyst_prompt(version: Optional[str] = None) -> str:
    """Load the analyst prompt. Defaults to the configured prompt_version."""
    return _read_prompt("analyst", version or prompt_version_default())


def list_prompt_versions(role: str) -> Dict[str, str]:
    """Return {version: path} for all prompt files for *role*."""
    dir_path = os.path.join(PROMPTS_ROOT, role)
    if not os.path.isdir(dir_path):
        return {}
    result = {}
    for fname in sorted(os.listdir(dir_path)):
        if fname.startswith(f"{role}_") and fname.endswith(".txt"):
            version = fname[len(f"{role}_"):-4]
            result[version] = os.path.join(dir_path, fname)
    return result