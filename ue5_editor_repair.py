"""Restore available native editor mesh geometry under existing missing anchors.
The original scene, batch membership and historical import reports remain unchanged.
"""
import json
from pathlib import Path
from collections import Counter
from ue5_blueprint import read_tables,require
from ue5_editor_scene import placement_records
from ue5_editor_components import placements
from ue5_editor_mesh import read_static,build_static
from project_session import hash_file,digest


def source_identity(path,package):
    meta,_,_,exports,_,_=read_tables(path)
    require(meta['ue5'] in (1016,1017),'Repair supports native UE5.6 editor meshes only')
    require(meta.get('package_name')==package,'Serialized package identity differs from referenced package')
    roots=[e for e in exports if not e['outer'] and e['kind']=='StaticMesh']
    require(len(roots)==1 and roots[0]['name']==package.rsplit('/',1)[-1],'StaticMesh export identity mismatch')


def record_index(content,path,include_components):
    data=placement_records(content,path);index={}
    def add(key,package,overrides):
        require(key not in index,'Ambiguous saved actor or component identity');index[key]=(package,overrides)
    for r in data['records']:add((r['source'],r['actor'],''),r['package'],r['overrides'])
    if include_components:
        actors,_=placements(content,path)
        for a in actors:
            for c in a['components']:
                if c['package']:add((a['source'],a['actor'],c['name']),c['package'],c['overrides'])
    return data['level'],index


def restore(filepath,anchors,materials=False,partial=False):
    """Create an independent overlay, with identity-local children of verified missing anchors.
    Historical job metadata is not changed. Existing repairs are never overwritten.
    """
    import bpy
    from mathutils import Matrix
    from uasset import UProject
    from project_session import new_ids,rollback_new
    path=Path(filepath).resolve();project=UProject(str(path));content=Path(project.dir)/'Content';anchors=list(dict.fromkeys(anchors))
    require(anchors and len(anchors)<=10000,'Select one or more missing mesh placeholders')
    level,index=record_index(content,path,any(a.get('UE_component_name') for a in anchors));results=[];cache={};pending=[];options_values=[bool(materials),bool(partial)]
    if materials:
        from ue5_editor_material import EDITOR_MATERIAL_REVISION
        options_values.append(EDITOR_MATERIAL_REVISION)
    options=digest(options_values)
    for a in anchors:
        record=dict(anchor=a.name,package=a.get('UE_mesh_package',''))
        try:
            require(a.type=='EMPTY' and a.get('UE_geometry_status')=='missing' and a.get('UE_preview_only'),'Not a native missing mesh placeholder')
            require(a.name in bpy.context.scene.objects,'Anchor not in current scene')
            owners=[]
            for c in a.users_collection:
                t=bpy.data.texts.get(c.get('UE_report',''))
                if not t:continue
                try:r=json.loads(t.as_string())
                except (ValueError,TypeError):continue
                if r.get('level')==level and 'actor_status' in r and 'dependencies' in r:owners.append(c)
            require(len(owners)==1,'Select an anchor from exactly one original imported map collection')
            original=owners[0];require(not original.get('UE_source_map_path') or Path(original['UE_source_map_path']).resolve()==path,'Original imported project differs from selected project')
            key=(a.get('UE_source_actor_package',''),a.get('UE_actor',''),a.get('UE_component_name',''));want=index.get(key)
            require(want is not None and want[0]==record['package'],'Saved actor or package association differs')
            overrides=json.loads(a.get('UE_material_override_packages','[]'));require(overrides==want[1],'Saved material override association differs')
            package=record['package'];prior=[o for o in a.children if o.get('UE_repair_child')];require(len(prior)<=1,'Multiple existing repair children; review manually')
            if package not in cache:
                try:
                    source=Path(project.resolve_package(package))
                    if not source.is_file():raise FileNotFoundError('Original package is still missing')
                    source_identity(source,package);sha=hash_file(source)
                    data=None if prior else read_static(source)
                    require(hash_file(source)==sha,'Package changed during inspection')
                    cache[package]=dict(path=source,sha=sha,data=data,status='available')
                except FileNotFoundError as exc:cache[package]=dict(status='still_missing',detail=str(exc))
                except Exception as exc:cache[package]=dict(status='unresolved',detail=f'{type(exc).__name__}: {exc}')
            entry=cache[package]
            if prior:
                child=prior[0]
                if entry['status']!='available' or child.type!='MESH' or child.get('UE_mesh_package')!=package or child.get('UE_repair_source_sha256')!=entry.get('sha') or child.get('UE_repair_options')!=options:
                    record.update(status='blocked_stale',detail='Existing repair differs from source or settings; review/remove it explicitly')
                else:record.update(status='existing_repair',object=child.name,detail='Existing child preserved; edited geometry/materials are not overwritten')
            elif entry['status']!='available':record.update(status=entry['status'],detail=entry['detail'])
            else:
                if entry['data'] is None:
                    try:
                        entry['data']=read_static(entry['path']);require(hash_file(entry['path'])==entry['sha'],'Package changed during decoding')
                    except Exception as exc:
                        entry.update(status='unresolved',detail=str(exc));raise
                require(len(overrides)<=len(entry['data']['materials']),'Override slots exceed recovered mesh materials')
                pending.append((a,entry,overrides,record,original));continue
        except Exception as exc:record.update(status='refused',detail=f'{type(exc).__name__}: {exc}')
        results.append(record)
    before=set(new_ids());overlay=None;mesh_cache={};override_cache={};material_report={}
    try:
        if pending:
            require(len({original.as_pointer() for _,_,_,_,original in pending})==1,'Repair anchors must share one original geometry collection')
            overlay=bpy.data.collections.new('UE5 recovered geometry — '+path.stem);pending[0][4].children.link(overlay);overlay['UE_repair_source_map']=str(path)
            for a,entry,overrides,record,original in pending:
                package=record['package']
                if package not in mesh_cache:
                    require(hash_file(entry['path'])==entry['sha'],'Package changed before build')
                    mesh=build_static(entry['data']);mesh['UE_mesh_package']=package;mesh_cache[package]=mesh
                obj=bpy.data.objects.new(a.name+' / recovered mesh',mesh_cache[package]);overlay.objects.link(obj);obj.parent=a;obj.matrix_parent_inverse=Matrix.Identity(4);obj.matrix_basis=Matrix.Identity(4)
                obj['UE_repair_child']=True;obj['UE_geometry_status']='reconstructed_repair';obj['UE_mesh_package']=package;obj['UE_repair_source_sha256']=entry['sha'];obj['UE_repair_options']=options;obj['UE_source_actor_package']=a['UE_source_actor_package'];obj['UE_actor']=a['UE_actor'];obj['UE_material_override_packages']=json.dumps(overrides)
                if a.get('UE_component_name'):obj['UE_component_name']=a['UE_component_name']
                for i,p in enumerate(overrides):
                    if not p:continue
                    if p not in override_cache:
                        mat=bpy.data.materials.new(p.rsplit('/',1)[-1]);mat['UE_material_package']=p;mat['UE_unresolved_material']=True;override_cache[p]=mat
                    obj.material_slots[i].link='OBJECT';obj.material_slots[i].material=override_cache[p]
                record.update(status='repaired',object=obj.name,source_sha256=entry['sha']);results.append(record)
            if materials:
                from ue5_editor_material import bind_slots
                material_report=bind_slots(overlay.objects,content,partial)
        report=dict(level=level,counts=dict(Counter(r['status'] for r in results)),results=results,materials=material_report,unique_meshes=len(mesh_cache),scope='Exact native editor package repair overlay; original anchor, user transforms and original batch metadata preserved. Reuse does not certify user-edited meshes or material dependencies.')
        text=bpy.data.texts.new(path.stem+' - missing mesh repair.json');text.write(json.dumps(report,indent=2));report['report_text']=text.name
        if overlay:overlay['UE_report']=text.name
        return overlay,report
    except Exception:
        rollback_new(before);raise
