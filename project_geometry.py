"""Unified native project geometry routing. Cooked layouts require an explicit profile."""
import json
from collections import Counter
from pathlib import Path

from skeleton_native import Reader, MAGIC


def split_root_class(path):
    """Inspect the root class of a supported tagged, unversioned split header."""
    path=Path(path)
    if path.stat().st_size>16*1024*1024: raise ValueError('Split header exceeds size limit')
    raw=path.read_bytes(); r=Reader(raw)
    if r.take(4)!=MAGIC or r.unpack('5i')!=(-7,0,0,0,0):
        raise NotImplementedError('Unsupported split package header')
    if r.i()!=len(raw) or r.string()!='None': raise ValueError('Invalid split header')
    flags=r.unpack('I')[0]
    if not flags&0x80000000 or flags&0x2000: raise NotImplementedError('Expected tagged cooked package')
    n,no,g,go,ec,eo,ic,io=r.unpack('8i')
    if not (0<n<=100000 and g==go==0 and 1<=ec<=4096 and 0<ic<=100000 and r.pos<=no<io<eo<len(raw) and io+28*ic==eo and eo+104*ec<=len(raw)):
        raise ValueError('Invalid split package tables')
    r.pos=no; names=[]
    for _ in range(n): names.append(r.string()); r.take(4)
    if r.pos!=io: raise ValueError('Invalid name table extent')
    imports=[(r.name(names),r.name(names),r.i(),r.name(names)) for _ in range(ic)]
    classes=[]
    for i in range(ec):
        r.pos=eo+104*i; ci,si,ti,outer=r.unpack('4i')
        if outer: continue
        if not -ic<=ci<0 or imports[-ci-1][:2]!=('/Script/CoreUObject','Class'):
            raise NotImplementedError('Unsupported root class reference')
        classes.append(imports[-ci-1][3])
    if len(classes)!=1: raise NotImplementedError('Expected one root asset class')
    return classes[0]


def load_static(path,project,profile):
    """Keep editor routing intact; route split static assets to the native decoder."""
    path=Path(path)
    if path.with_suffix('.uexp').is_file():
        from cooked_static import read_static,build_static
        return build_static(read_static(path,profile))
    import uasset,umesh
    asset=uasset.UAsset(str(path),False,project)
    try:
        asset.Read(False)
        exports=[e for e in asset.exports if e.export_class_type=='StaticMesh']
        if len(exports)!=1: raise NotImplementedError('Expected one StaticMesh export')
        return umesh.ImportStaticMesh(exports[0],import_materials=False,log=False)
    finally: asset.Close()


def root_class(path,project):
    if path.with_suffix('.uexp').is_file(): return split_root_class(path)
    from package_inspector import inspect_package
    import uasset
    meta=inspect_package(path)
    if meta.get('status')!='tables_inspected' or meta.get('legacy')!=-7:
        raise NotImplementedError('Unsupported editor package: '+meta.get('status','unknown'))
    asset=uasset.UAsset(str(path),False,project)
    try:
        asset.Read(False)
        roots=[e.export_class_type for e in asset.exports if e.outer_index==0 and e.export_class_type!='MetaData']
        if len(roots)!=1: raise NotImplementedError('Expected one root editor asset')
        return roots[0]
    finally: asset.Close()


def import_geometry_folder(descriptor,subfolder='',profile='4.27'):
    """Import supported geometry assets as a gallery, not as a level layout."""
    import bpy,uasset
    from skeletal_mesh_native import read_native_mesh,build_mesh
    from uproject_browser import discover_maps
    if profile not in ('4.18','4.27'): raise ValueError('Select an explicit cooked profile')
    descriptor,_,_=discover_maps(descriptor)
    content=(Path(descriptor).parent/'Content').resolve()
    folder=(content/subfolder).resolve()
    if not folder.is_relative_to(content) or not folder.is_dir(): raise ValueError('Select a folder inside project Content')
    paths=sorted(p for p in folder.rglob('*.uasset') if p.is_file() and p.resolve().is_relative_to(content) and not any(k in ('__ExternalActors__','__ExternalObjects__') for k in p.relative_to(content).parts))
    if len(paths)>10000: raise ValueError('Select a smaller folder (maximum 10000 packages)')
    project=uasset.UProject(descriptor); collection=bpy.data.collections.new('UE native geometry gallery')
    bpy.context.scene.collection.children.link(collection)
    records=[]; cursor=0.; totals=Counter()
    stores=(bpy.data.objects,bpy.data.meshes,bpy.data.armatures,bpy.data.materials)
    for path in paths:
        package='/Game/'+path.relative_to(content).with_suffix('').as_posix()
        record={'package':package}; before=None
        try:
            kind=root_class(path,project); record['class']=kind
            if kind not in ('StaticMesh','SkeletalMesh'):
                record['status']='skipped_non_geometry'; continue
            before={item.as_pointer() for store in stores for item in store}
            if kind=='StaticMesh':
                mesh=load_static(path,project,profile)
                obj=bpy.data.objects.new(mesh.name,mesh); collection.objects.link(obj); root=obj
            else:
                obj,root=build_mesh(read_native_mesh(path,profile),collection); mesh=obj.data
            if not len(mesh.vertices) or not len(mesh.polygons): raise ValueError('Empty native geometry')
            # A gallery offset is explicit, leaving source mesh coordinates and skin unchanged.
            lo=min(v.co.x for v in mesh.vertices); hi=max(v.co.x for v in mesh.vertices)
            root.location.x=cursor-lo; cursor+=hi-lo+0.5
            obj['UE_mesh_package']=package; obj['UE_geometry_status']='reconstructed'
            root['UE_gallery_offset_x']=root.location.x
            record.update(status='reconstructed',vertices=len(mesh.vertices),triangles=len(mesh.polygons),bones=len(root.data.bones) if kind=='SkeletalMesh' else 0,object=obj.name)
            totals.update({k:record[k] for k in ('vertices','triangles','bones')})
        except Exception as exc:
            if before is not None:
                created=[item for store in stores for item in store if item.as_pointer() not in before]
                if created: bpy.data.batch_remove(ids=created)
            record.update(status='unsupported' if isinstance(exc,NotImplementedError) else 'failed',detail=f'{type(exc).__name__}: {exc}')
        finally: records.append(record)
    report={'profile':profile,'folder':folder.relative_to(content).as_posix(),'layout':'inspection gallery, not level placement','counts':dict(Counter(r['status'] for r in records)),'totals':dict(totals),'assets':records}
    text=bpy.data.texts.new(collection.name+' - report.json'); text.write(json.dumps(report,indent=2)); collection['UE_report']=text.name
    return collection,report
