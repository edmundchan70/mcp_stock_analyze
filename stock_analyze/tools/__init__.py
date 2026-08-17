"""Component graph tool registry (T13).

Importing this package registers the 4 built-in components in
:data:`REGISTRY`. ``get_tools()``/``registry_payload()`` serve the palette;
``validate_registry()`` is the startup check; ``run_graph`` executes a
graph definition via :mod:`stock_analyze.tools.walker`.
"""

from .builtins import QUANT, REPORT, SCANNER, SEARCH  # noqa: F401 (registers)
from .merge import merge_rows, symbol_key, to_merge_table
from .protocol import (
    ERROR_KEY,
    INPUT_ACCEPTS,
    PORT_STAGES,
    PortDef,
    ToolSpec,
    VariableDef,
    stage_accepts,
)
from .registry import (
    REGISTRY,
    get_tool,
    get_tools,
    register,
    registry_payload,
    validate_registry,
)
from .walker import (
    GraphRunResult,
    GraphValidationError,
    NodeResult,
    default_params,
    run_graph,
    topological_order,
    validate_graph,
)

__all__ = [
    "ERROR_KEY",
    "INPUT_ACCEPTS",
    "PORT_STAGES",
    "PortDef",
    "QUANT",
    "REGISTRY",
    "REPORT",
    "SCANNER",
    "SEARCH",
    "ToolSpec",
    "VariableDef",
    "default_params",
    "get_tool",
    "get_tools",
    "merge_rows",
    "register",
    "registry_payload",
    "run_graph",
    "stage_accepts",
    "symbol_key",
    "to_merge_table",
    "topological_order",
    "validate_graph",
    "validate_registry",
]
