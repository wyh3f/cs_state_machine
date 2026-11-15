"""代码生成层入口：按风格分发"""

from generator.base import GenerationResult, GeneratedFile, Issue
from generator.gen_goto_fsm import generate_lite

__all__ = [
    "GenerationResult", "GeneratedFile", "Issue", "generate_lite",
]
