"""Source-backed material slot diagnostics, not a claim of render completeness."""
from collections import Counter, deque


def material_gaps(materials, dependencies, scene_materials=()):
    edges=dependencies.get('dependencies',{});records=dependencies.get('records',{})
    rows=[]
    combined={p:dict(v,uses=['mesh_slot']) for p,v in materials.items()}
    for package,kind in scene_materials:
        if not package:continue
        record=combined.setdefault(package,dict(status='not_reconstructed',uses=[]))
        if kind not in record['uses']:record['uses'].append(kind)
    for package, material in sorted(combined.items()):
        if material.get('status')=='supported_pbr_subset' and material['uses']==['mesh_slot']:continue
        pending=deque([package]);seen=set();missing={};unknown=[]
        while pending:
            ref=pending.popleft()
            if ref in seen:continue
            seen.add(ref)
            edge=edges.get(ref)
            if edge and edge['status']!='available':
                missing[ref]=edge['status'];continue
            rec=records.get(ref)
            if rec is None or rec.get('coverage')=='unknown' or rec.get('soft_coverage')=='unknown':unknown.append(ref)
            if rec:
                # Only hard dependencies are attributable to this saved package closure.
                pending.extend(r for r in rec.get('references',[]) if r.startswith(('/Game/','/Engine/')) and r not in seen)
        rows.append(dict(package=package,status=material.get('status','unknown'),uses=material['uses'],use_status={kind:material.get('status','unknown') if kind=='mesh_slot' else 'not_reconstructed' for kind in material['uses']},missing_hard_closure=missing,unknown_tables=sorted(unknown),detail=material.get('detail',''),issues=material.get('issues',[]),action='Review exact original package recovery or matching Engine Content, then reimport; unsupported rendering may remain' if missing else 'Inspect unsupported expressions or unavailable source tables; no substitute inferred'))
    return dict(materials=rows,status_counts=dict(Counter(r['status'] for r in rows)),distinct_missing_packages=sorted({p for r in rows for p in r['missing_hard_closure']}),scope='Unresolved or partial bound material packages and saved decal/landscape material references; known hard closure only. A missing reference is not proof it contributes to visible shading; soft/plugin references remain in source dependency report.')
