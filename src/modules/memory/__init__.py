"""Memory module package."""

try:
    from .memory_gateway import MemoryGateway, MemoryRecord
except Exception:  # optional in lightweight/script contexts
    MemoryGateway = None
    MemoryRecord = None

try:
    from .providers import MemoryProvider, RecallItem, RecallResult, NativeMemoryProvider
except Exception:  # optional in lightweight/script contexts
    MemoryProvider = None
    RecallItem = None
    RecallResult = None
    NativeMemoryProvider = None

__all__ = [
    "MemoryGateway",
    "MemoryRecord",
    "MemoryProvider",
    "RecallItem",
    "RecallResult",
    "NativeMemoryProvider",
]
