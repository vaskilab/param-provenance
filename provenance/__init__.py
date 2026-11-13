"""param-provenance: catch fabricated tool arguments before they execute.

Schema validation checks the shape of a value. Provenance checks its origin.
"""

from .checker import (
    PARAM_FABRICATION,
    REF_UNRESOLVED,
    CheckResult,
    Violation,
    check_call,
)
from .rules import ABORT, WARN, RuleError, RuleSet, SourceRule
from .trace import (
    REF_KEY,
    RefError,
    ToolCall,
    ToolResult,
    Trace,
    extract,
    is_ref,
    resolve_args,
    resolve_ref,
)

__version__ = "0.1.0"

__all__ = [
    "CheckResult",
    "Violation",
    "check_call",
    "PARAM_FABRICATION",
    "REF_UNRESOLVED",
    "RuleSet",
    "SourceRule",
    "RuleError",
    "ABORT",
    "WARN",
    "Trace",
    "ToolCall",
    "ToolResult",
    "RefError",
    "REF_KEY",
    "extract",
    "is_ref",
    "resolve_ref",
    "resolve_args",
    "__version__",
]
