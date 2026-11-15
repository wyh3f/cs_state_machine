"""代码生成层入口：按风格分发"""

from generator.base import GenerationResult, GeneratedFile, Issue
from generator.gen_goto_fsm import generate_lite
from generator.gen_event_fsm import generate_full

__all__ = [
    "GenerationResult", "GeneratedFile", "Issue", "generate_lite",
    "generate_full",
]
