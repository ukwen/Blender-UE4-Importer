"""Conservative serialized Blueprint ancestry resolution.

Parent references are class/package pairs. Explicit child bindings (including null)
win. Inherited binding candidates are available for map-owned components only;
no child component creation, runtime graph execution or inherited override guessing.
"""
from copy import deepcopy


def resolve_lineage(key, load, maximum=32):
    chain=[]; seen=set(); current=key; status='native_parent'; detail=''
    while True:
        if current in seen or len(chain)>=maximum:
            status='unresolved';detail='Blueprint ancestry cycle or depth limit';break
        seen.add(current); local=load(current)
        if local.get('status')!='inspected':
            status='unresolved';detail=f"{current[0]}: {local.get('detail',local.get('status'))}";break
        chain.append((current,local))
        pkg,name=local.get('parent_blueprint'),local.get('parent_class')
        if pkg and pkg.startswith('/Script/') and name: break
        if not pkg or not name or not pkg.startswith(('/Game/','/Engine/')) or not name.endswith('_C'):
            status='unresolved'; detail='Unsupported or missing superclass identity';break
        current=(pkg,name)
    # Missing/invalid ancestor: expose diagnostics, use only local declarations.
    bindings={}; conflicts=[]
    for source,local in reversed(chain if status=='native_parent' else chain[:1]):
        for name,entry in local['bindings'].items():
            item=deepcopy(entry); item['declared_in']=source[0]
            inherited=bindings.get(name)
            if inherited and inherited['class']!=item['class']:
                conflicts.append(name);bindings.pop(name,None);continue
            # Only use an inherited mesh when the child explicitly associates
            # the same CDO template and omits the mesh field. No SCS override inference.
            if (inherited and not item['explicit'] and inherited['explicit'] and
                    item['origin']==inherited['origin']=='CDO' and item['template']==inherited['template']):
                item.update(package=inherited['package'],explicit=True,mesh_declared_in=inherited.get('mesh_declared_in',inherited['declared_in']))
            else: item['mesh_declared_in']=source[0]
            bindings[name]=item
    # Inherited SCS entries need InheritableComponentHandler override support.
    # Do not activate them just because the ancestor declares them.
    root=chain[0][1]['bindings'] if chain else {}
    for name in list(bindings):
        if name not in root: bindings.pop(name,None)
    for name in conflicts: bindings.pop(name,None)
    return dict(lineage=[{'package':k[0],'class':k[1]} for k,_ in chain],lineage_status=status,
                lineage_detail=detail,bindings=bindings,binding_conflicts=sorted(set(conflicts)))
