from snapfix.serializer import SnapfixSerializer

_global_serializer = SnapfixSerializer()


def reconstruct(data):
    """Restore __snapfix_type__ markers in a captured fixture to Python types."""
    return _global_serializer.deserialize(data)
