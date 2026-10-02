"""Prompt versioning loader.

Loads versioned prompt files from the prompts/ directory.
Each agent role (tutor, evaluator, learner, analyst) has its own subdirectory.

A prompt version names a file: version ``v2`` for the tutor lives at
``prompts/tutor/tutor_v2.txt``. :data:`DEFAULT_PROMPT_VERSION` is the version
used when the environment does not name one, so the loader and the files on
disk cannot disagree — which they previously could, leaving the loader looking
for a file that was never written.
"""

import os
from typing import Dict, Optional

from .config import PROJECT_ROOT, prompt_version_default
from .errors import ConfigurationError

PROMPTS_ROOT = os.path.join(PROJECT_ROOT, "prompts")

#: Prompt version resolved when no version is configured.
DEFAULT_PROMPT_VERSION = "v1"


def _read_prompt(role: str, version: str) -> str:
    path = os.path.join(PROMPTS_ROOT, role, f"{role}_{version}.txt")
    if not os.path.isfile(path):
        available = sorted(list_prompt_versions(role)) or ["none"]
        raise ConfigurationError(
            f"No {role} prompt for version {version!r}: expected {path}. "
            f"Available versions: {', '.join(available)}."
        )
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _resolve_version(version: Optional[str]) -> str:
    """Return the prompt version to load.

    ``EKAGRA_PROMPT_VERSION`` wins when set, because a run must be able to pin
    the exact prompt it used. Otherwise the default version is used. The
    foundation's own configuration stamp is *not* a prompt version — it labels
    the configuration, not the text sent to the model — so it is never used to
    locate a file.
    """
    if version:
        return version
    return DEFAULT_PROMPT_VERSION


def load_tutor_prompt(version: Optional[str] = None) -> str:
    """Load the tutor prompt. Defaults to the configured prompt version."""
    return _read_prompt("tutor", _resolve_version(version))


def load_evaluator_prompt(version: Optional[str] = None) -> str:
    """Load the evaluator prompt. Defaults to the configured prompt version."""
    return _read_prompt("evaluator", _resolve_version(version))


def load_learner_prompt(version: Optional[str] = None) -> str:
    """Load the learner (simulated) prompt. Defaults to the configured prompt version."""
    return _read_prompt("learner", _resolve_version(version))


def load_analyst_prompt(version: Optional[str] = None) -> str:
    """Load the analyst prompt. Defaults to the configured prompt version."""
    return _read_prompt("analyst", _resolve_version(version))


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