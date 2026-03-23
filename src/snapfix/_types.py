"""
Internal sentinel types used by the serializer.

These are embedded into serialized dicts as marker keys.
They are NOT part of the public API — do not depend on their exact values
in application code. The format may change before v1.0.0.
"""

# Marker key used in all type-annotated serialized dicts
SNAPFIX_TYPE_KEY = "__snapfix_type__"

# Emitted when an object cannot be serialized
SNAPFIX_UNSERIALIZABLE_KEY = "__snapfix_unserializable__"

# Emitted when a circular reference is detected
SNAPFIX_CIRCULAR_KEY = "__snapfix_circular__"

# Emitted when the payload exceeds max_size_bytes
SNAPFIX_TRUNCATED_KEY = "__snapfix_truncated__"

# Emitted when the object exceeds max_depth
SNAPFIX_MAXDEPTH_KEY = "__snapfix_maxdepth__"

# The string used to replace scrubbed string fields
SCRUBBED_STR = "***SCRUBBED***"

# The integer used to replace scrubbed numeric fields
SCRUBBED_NUM = -1
