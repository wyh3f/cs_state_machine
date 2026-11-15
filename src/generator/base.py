"""代码生成层公共结构：问题项、生成文件、命名与校验工具"""

from dataclasses import dataclass, field

# C89/C99/C11 关键字，状态名与工程名都不能与之冲突
C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while",
    "_Bool", "_Complex", "_Imaginary",
}


@dataclass
class Issue:
    """一条校验问题；level 为 error 或 warning"""
    level: str
    message: str


@dataclass
class GeneratedFile:
    name: str
    content: str


@dataclass
class GenerationResult:
    files: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors

    def add_error(self, message):
        self.errors.append(Issue("error", message))

    def add_warning(self, message):
        self.warnings.append(Issue("warning", message))


def is_c_identifier(text):
    """判断是否为合法 C 标识符（不含关键字检查）"""
    if not text or not isinstance(text, str):
        return False
    if not (text[0].isalpha() or text[0] == "_"):
        return False
    return all(ch.isalnum() or ch == "_" for ch in text)


def is_valid_name(text):
    """合法且不是 C 关键字"""
    return is_c_identifier(text) and text not in C_KEYWORDS


def sanitize_identifier(text, fallback="fsm"):
    """把任意文本转成合法 C 标识符，用于工程名派生的函数名/文件名"""
    chars = []
    for ch in text or "":
        if ch.isascii() and (ch.isalnum() or ch == "_"):
            chars.append(ch)
        else:
            chars.append("_")
    name = "".join(chars).strip("_")
    if not name:
        name = fallback
    # 纯数字（例如中文工程名只剩编号）时补一个可读前缀
    if not any(ch.isalpha() for ch in name):
        name = f"{fallback}_{name}"
    if name[0].isdigit():
        name = "s_" + name
    if name in C_KEYWORDS:
        name += "_sm"
    return name


def indent_lines(text, prefix):
    """把多行文本整体缩进；空行保持为空"""
    out = []
    for line in (text or "").splitlines():
        out.append((prefix + line) if line.strip() else "")
    return "\n".join(out)
