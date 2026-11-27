"""Conservative inventory of saved instance components, not a native decoder."""
from collections import Counter

KINDS = frozenset(('InstancedStaticMeshComponent', 'HierarchicalInstancedStaticMeshComponent',
                   'FoliageInstancedStaticMeshComponent'))


def scan_exports(exports, ref, package, source, level, inline):
    """Only attribute components to actors owned by this exact PersistentLevel.

    Never interpret a component export as a count of instances. Report unknown
    ownership separately, including construction templates and corrupt chains.
    """
    records = []
    for index, component in enumerate(exports, 1):
        if component['kind'] not in KINDS:
            continue
        row = dict(source=source, component=component['name'], export_index=index,
                   kind=component['kind'], status='unverified_ownership', instance_count=None)
        seen = {index}
        owner = component['outer']
        try:
            while owner > 0 and owner not in seen:
                seen.add(owner)
                actor = ref(owner)
                outer = actor['outer']
                parent = ref(outer) if outer else None
                if parent and parent['kind'] == 'Level' and parent['name'] == 'PersistentLevel':
                    if (inline and outer > 0) or (not inline and outer < 0 and package(outer) == level):
                        row.update(actor=actor['name'], actor_export_index=owner,
                                   status='unsupported_native_instance_payload')
                    else:
                        row['status'] = 'different_level'
                    break
                owner = outer
        except (KeyError, IndexError, TypeError, ValueError):
            row['status'] = 'unverified_ownership'
        records.append(row)
    return records


def summarize(records, inventory_errors):
    return dict(components=len(records), status=dict(Counter(r['status'] for r in records)),
                classes=dict(Counter(r['kind'] for r in records)), records=records,
                inventory_complete=not inventory_errors,
                scope='Saved component exports only. Instance payloads and counts not decoded; runtime/PCG instances not enumerated.')
