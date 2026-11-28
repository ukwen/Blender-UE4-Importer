"""Unified native project geometry routing. Cooked layouts require an explicit profile."""
from project_paths import ProjectPaths

import json
from collections import Counter
from pathlib import Path

from skeleton_native import Reader, MAGIC


def split_root_class(path):
    """Inspect the root class of a supported tagged, unversioned split header."""
    path=Path(path)
    if path.stat().st_size>16*1024*1024: raise ValueError('Split header exceeds size limit')
    raw=path.read_bytes(); r=Reader(raw)
    if raw[:8] in (MAGIC+b'\xf8\xff\xff\xff',MAGIC+b'\xf7\xff\xff\xff'):
        from ue5_cooked_geometry import package
        from ue5_modern_static import package as modern_package
        if raw[4:8]==b'\xf8\xff\xff\xff':
            try: return package(path)[0]
            except (ValueError,NotImplementedError): pass
        return modern_package(path)[0]
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
    from package_inspector import inspect_package
    meta=inspect_package(path)
    if meta.get('ue5') in (1016,1017):
        from ue5_editor_mesh import read_static,build_static
        return build_static(read_static(path))
    if meta.get('ue5') is not None:
        raise NotImplementedError('UE5 editor static geometry profile not supported')
    if meta.get('ue4') == 508:
        from legacy_static import read_legacy_static_path,build_legacy_static
        return build_legacy_static(read_legacy_static_path(path))
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
    meta=inspect_package(path)
    if (meta.get('status')=='tables_inspected' and meta.get('ue4') in (508,522) and
        (meta.get('ue5') is None or meta['ue5']==1004 or 1012<=meta['ue5']<=1018)):
        from package_records import read_package
        _,_,table=read_package(path)
        roots=[e for e in table.exports if not e.outer and e.kind!='MetaData']
        primary=[e for e in roots if e.kind=='SkeletalMesh']
        if len(primary)==1:
            roots=[e for e in roots if not (e.kind=='SkeletalMeshEditorData' and e.name==primary[0].name+'_USkeletalMeshEditorData')]
        if len(roots)==1:return roots[0].kind
        raise NotImplementedError('Expected one root editor asset')
    if meta.get('status')!='tables_inspected' or meta.get('legacy')!=-7:
        raise NotImplementedError('Unsupported editor package: '+meta.get('status','unknown'))
    import uasset
    asset=uasset.UAsset(str(path),False,project)
    try:
        asset.Read(False)
        roots=[e for e in asset.exports if e.outer_index==0 and e.export_class_type!='MetaData']
        primary=[e for e in roots if e.export_class_type=='SkeletalMesh']
        if len(primary)==1:
            roots=[e for e in roots if not (e.export_class_type=='SkeletalMeshEditorData' and e.object_name==primary[0].object_name+'_USkeletalMeshEditorData')]
        roots=[e.export_class_type for e in roots]
        if len(roots)!=1: raise NotImplementedError('Expected one root editor asset')
        return roots[0]
    finally: asset.Close()


class _NonGeometry(Exception): pass

def iter_geometry_folder(descriptor,subfolder='',profile='4.27',include_physics=False,planned_paths=None,all_lods=False,editor_materials=False,partial_materials=False):
    """Import supported geometry assets as a gallery, not as a level layout."""
    import bpy
    from skeletal_mesh_native import read_native_mesh,build_mesh
    from project_paths import discover_maps
    if profile not in ('4.18','4.27','5.0','5.4','5.5','5.6'): raise ValueError('Select an explicit cooked profile')
    descriptor,_,_=discover_maps(descriptor)
    content=(Path(descriptor).parent/'Content').resolve()
    folder=(content/subfolder).resolve()
    if not folder.is_relative_to(content) or not folder.is_dir(): raise ValueError('Select a folder inside project Content')
    paths=sorted(p for p in folder.rglob('*.uasset') if p.is_file() and p.resolve().is_relative_to(content) and not any(k in ('__ExternalActors__','__ExternalObjects__') for k in p.relative_to(content).parts))
    if planned_paths is not None:
        allowed=set(paths); paths=[Path(p) for p in planned_paths]
        if len(set(paths))!=len(paths) or any(p not in allowed for p in paths): raise ValueError('Stale or invalid planned package paths')
    if len(paths)>10000: raise ValueError('Select a smaller folder (maximum 10000 packages)')
    project=ProjectPaths(descriptor); collection=bpy.data.collections.new('UE native geometry gallery')
    bpy.context.scene.collection.children.link(collection)
    records=[]; cursor=0.; totals=Counter()
    stores=(bpy.data.objects,bpy.data.meshes,bpy.data.armatures,bpy.data.materials,bpy.data.images)
    material_cache={}
    for path in paths:
        package='/Game/'+path.relative_to(content).with_suffix('').as_posix()
        record={'package':package}; before=None
        try:
            kind=root_class(path,project); record['class']=kind
            if kind not in ('StaticMesh','SkeletalMesh'):
                raise _NonGeometry()
            before={item.as_pointer() for store in stores for item in store}
            if kind=='StaticMesh':
                mesh=load_static(path,project,profile)
                obj=bpy.data.objects.new(mesh.name,mesh); collection.objects.link(obj); root=obj
            else:
                if all_lods and profile=='5.6' and path.with_suffix('.uexp').is_file():
                    from skeletal_lod_group import build_lod_group
                    root,group=build_lod_group(path,collection);obj=group[0]
                    record['lods']=[{'lod':i,'vertices':len(o.data.vertices),'triangles':len(o.data.polygons)} for i,o in enumerate(group)]
                    for o in group: o['UE_mesh_package']=package; o['UE_geometry_status']='reconstructed'
                elif not path.with_suffix('.uexp').is_file():
                    from package_inspector import inspect_package
                    if inspect_package(path).get('ue5') in (1016,1017):
                        from ue5_editor_mesh import read_skeletal,build_skeletal
                        obj,root=build_skeletal(read_skeletal(path),collection)
                    else: obj,root=build_mesh(read_native_mesh(path,profile),collection)
                else: obj,root=build_mesh(read_native_mesh(path,profile),collection)
                mesh=obj.data
            if not len(mesh.vertices) or not len(mesh.polygons): raise ValueError('Empty native geometry')
            # A gallery offset is explicit, leaving source mesh coordinates and skin unchanged.
            lo=min(v.co.x for v in mesh.vertices); hi=max(v.co.x for v in mesh.vertices)
            root.location.x=cursor-lo; cursor+=hi-lo+0.5
            obj['UE_mesh_package']=package; obj['UE_geometry_status']='reconstructed'
            root['UE_gallery_offset_x']=root.location.x
            record.update(status='reconstructed',vertices=len(mesh.vertices),triangles=len(mesh.polygons),bones=len(root.data.bones) if kind=='SkeletalMesh' else 0,object=obj.name)
            if 'UE_geometry_scope' in mesh:
                record.update(geometry_scope=mesh['UE_geometry_scope'],external_bulk_bytes=mesh.get('UE_external_bulk_bytes',0))
            if profile in ('5.0','5.4','5.5','5.6') and path.with_suffix('.uexp').is_file():
                from ue5_cooked_material import inspect_material_slots
                record['material_instances']=inspect_material_slots(mesh,project,profile)
            if editor_materials and mesh.get('UE_source_format') in ('UE5 editor FMeshDescription','UE5 editor skinned FMeshDescription'):
                from ue5_editor_material import bind_slots
                record['editor_materials']=bind_slots([obj],content,partial_materials,material_cache)
            totals.update({k:record[k] for k in ('vertices','triangles','bones')})
            if include_physics and kind=='SkeletalMesh':
                from physics_native import associate_physics
                try: record['physics']=associate_physics(root,path,content)
                except Exception as exc: record['physics']={'status':'unavailable','detail':f'{type(exc).__name__}: {exc}'}
        except _NonGeometry:
            record['status']='skipped_non_geometry'
        except Exception as exc:
            if before is not None:
                created=[item for store in stores for item in store if item.as_pointer() not in before]
                if created: bpy.data.batch_remove(ids=created)
            record.update(status='unsupported' if isinstance(exc,NotImplementedError) else 'failed',detail=f'{type(exc).__name__}: {exc}')
        finally: records.append(record)
        yield collection, _gallery_report(profile,folder,content,records,totals)
    return collection,_gallery_report(profile,folder,content,records,totals)

def _gallery_report(profile,folder,content,records,totals):
    report={'profile':profile,'folder':folder.relative_to(content).as_posix(),'layout':'inspection gallery, not level placement','counts':dict(Counter(r['status'] for r in records)),'totals':dict(totals),'physics_counts':dict(Counter(r['physics']['status'] for r in records if 'physics' in r)),'assets':records}
    return report

def finish_gallery(collection,report):
    import bpy
    text=bpy.data.texts.new(collection.name+' - report.json'); text.write(json.dumps(report,indent=2)); collection['UE_report']=text.name
    return collection,report

def import_geometry_folder(descriptor,subfolder='',profile='4.27',include_physics=False,all_lods=False,editor_materials=False,partial_materials=False):
    iterator=iter_geometry_folder(descriptor,subfolder,profile,include_physics,all_lods=all_lods,editor_materials=editor_materials,partial_materials=partial_materials)
    while True:
        try: next(iterator)
        except StopIteration as stop: return finish_gallery(*stop.value)
