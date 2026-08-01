"""SignalCloud universal Playbook authoring and compilation helpers."""

from .codec import load_playbook, save_playbook, validate_playbook
from .evaluator import evaluate_playbook
from .model import PlaybookValidationError


def compile_playbook_runtime(*args, **kwargs):
    from .compiler import compile_playbook_runtime as compile_runtime
    return compile_runtime(*args, **kwargs)


__all__ = [
    "PlaybookValidationError",
    "compile_playbook_runtime",
    "evaluate_playbook",
    "load_playbook",
    "save_playbook",
    "validate_playbook",
]
