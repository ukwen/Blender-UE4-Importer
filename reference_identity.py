"""Resolve package identity from native typed map references only.

Legacy import objects are not accepted by native consumers. The package table
owns validation of indices, package kinds and outer cycles.
"""
from classic_map_records import MapEntry


def package_reference(ref):
    if not isinstance(ref, MapEntry):
        return ''
    return ref.package_identity
