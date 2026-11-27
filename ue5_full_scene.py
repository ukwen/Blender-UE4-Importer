"""One-operation native saved-level reconstruction, with explicit coverage and atomic ownership."""
import json
from pathlib import Path
from collections import Counter
from ue5_blueprint import read_tables, require
from ue5_editor_scene import external_packages


def actor_inventory(content, path):
    """Inventory serialized direct PersistentLevel exports, not an Unreal runtime actor count."""
    content=Path(content).resolve();path=Path(path).resolve()
    level='/Game/'+path.relative_to(content).with_suffix('').as_posix()
    meta,_,_,exports,_,_=read_tables(path)
    require(meta['ue5'] in (1016,1017) and any(e['kind']=='World' and not e['outer'] for e in exports),'Full scene currently supports the tested UE5.6 editor World profile')
    found=[];errors=[]
    for source in [path,*external_packages(content,path)]:
        rel=source.relative_to(content).as_posix()
        try:
            _,_,_,exports,ref,pkg=read_tables(source)
            for e in exports:
                outer=e['outer']
                if not outer:continue
                parent=ref(outer)
                if not parent or parent['kind']!='Level' or parent['name']!='PersistentLevel':continue
                if not ((source==path and outer>0) or (source!=path and outer<0 and pkg(outer)==level)):continue
                found.append(dict(source=rel,actor=e['name'],kind=e['kind']))
        except Exception as exc:errors.append(dict(source=rel,detail=str(exc)))
    return found,errors


def coverage(inventory,objects):
    statuses={}
    for obj in objects:
        key=(obj.get('UE_source_actor_package'),obj.get('UE_actor'))
        if not all(key):continue
        if obj.type in ('MESH','ARMATURE'):kind='geometry'
        elif obj.type=='LIGHT':kind='light_preview'
        elif obj.type=='CAMERA':kind='camera_preview'
        elif obj.get('UE_geometry_status') in ('missing','unsupported','failed'):kind='unresolved_geometry'
        else:kind='anchor_or_marker'
        statuses.setdefault(key,set()).add(kind)
    rows=[dict(r,representation=sorted(statuses.get((r['source'],r['actor']),{'not_reconstructed'}))) for r in inventory]
    counts=Counter(s for r in rows for s in r['representation'])
    return dict(serialized_level_exports=len(rows),representation_counts=dict(counts),records=rows,unrepresented_classes=dict(Counter(r['kind'] for r in rows if r['representation']==['not_reconstructed'])),scope='Counts overlap; markers and unresolved anchors are not reconstructed geometry. Direct saved level exports only, not runtime actors.')


def reconstruct(filepath,partial=False,preview_scale=1.,strict_dependencies=False):
    import bpy
    from mathutils import Matrix
    from uasset import UProject
    from project_session import new_ids,rollback_new
    from ue5_editor_scene import reconstruct as geometry
    from ue5_editor_lighting import records as lights, reconstruct as lighting
    from ue5_editor_camera import records as cameras, reconstruct as camera
    path=Path(filepath).resolve();project=UProject(str(path));content=Path(project.dir)/'Content';scene=bpy.context.scene
    # Refuse overlapping independent imports too, rather than quietly duplicate or delete them.
    keys=('UE_full_scene_source','UE_source_map_path','UE_lighting_source','UE_camera_source')
    require(not any(str(path)==c.get(k) for c in scene.collection.children_recursive for k in keys),'Level already imported (full or separate stages); remove the prior import explicitly before retrying')
    from ue5_scene_dependencies import audit
    dependencies=audit(project,path)
    require(not strict_dependencies or dependencies['ready_for_strict_import'],
            f"Source dependency check failed: {dependencies['unresolved_hard']} hard, {dependencies['unresolved_soft_only']} soft-only unresolved, {len(dependencies['unknown_tables'])} unknown tables. Run Analyze Level Dependencies or disable strict mode.")
    inventory,errors=actor_inventory(content,path)
    light_data=lights(content,path);camera_data=cameras(content,path)
    before=set(new_ids());old_camera=scene.camera
    try:
        root=bpy.data.collections.new('UE Scene — '+path.stem);scene.collection.children.link(root)
        def nest(c,name):
            root.children.link(c);scene.collection.children.unlink(c);c.name=name
        geo,gr=geometry(str(path),materials=True,components=True,partial=partial);nest(geo,path.stem+' — Geometry and characters')
        stages={'geometry':gr};counts={'geometry_objects':len(geo.all_objects)}
        for name,data,build in [('lighting',light_data,lambda:lighting(str(path),preview_scale)),('cameras',camera_data,lambda:camera(str(path)))]:
            if not data['records']:
                stages[name]=dict(data,status='no_supported_records');counts[name+'_objects']=0;continue
            c,r=build();nest(c,path.stem+' — '+name.title());stages[name]=dict(r,status='preview');counts[name+'_objects']=len(c.all_objects)
        # Match exact source actor identity and the saved root transform before attaching the preview.
        anchors={(o.get('UE_source_actor_package'),o.get('UE_actor')):o for o in geo.objects if o.get('UE_character_record')}
        bpy.context.view_layer.update();linked=0;unlinked=[]
        for o in root.all_objects:
            if not o.get('UE_camera_component') or o.parent is not None:continue
            key=(o.get('UE_source_actor_package'),o.get('UE_actor'));a=anchors.get(key)
            if a is None:continue
            if max(abs(o.matrix_world[i][j]-a.matrix_world[i][j]) for i in range(4) for j in range(4))>1e-5:
                unlinked.append(dict(source=key[0],actor=key[1],detail='Saved camera and skeletal root transforms differ'));continue
            o.parent=a;o.matrix_parent_inverse=Matrix.Identity(4);o.matrix_basis=Matrix.Identity(4);linked+=1
        bpy.context.view_layer.update()
        require(scene.camera==old_camera,'Unexpected active camera change')
        objects=list(root.all_objects);require(objects,'No supported scene objects reconstructed')
        material_counts=Counter(v['status'] for v in gr.get('material_report',{}).values())
        report=dict(source=str(path),status='bounded_scene_preview',stages=stages,counts=dict(counts,objects=len(objects),meshes=sum(o.type=='MESH' for o in objects),armatures=sum(o.type=='ARMATURE' for o in objects),lights=sum(o.type=='LIGHT' for o in objects),cameras=sum(o.type=='CAMERA' for o in objects)),coverage=coverage(inventory,objects),source_dependencies=dependencies,strict_dependencies=strict_dependencies,inventory_errors=errors,material_status=dict(material_counts),linked_character_cameras=linked,unlinked_character_cameras=unlinked,scope='Saved geometry, supported components, material subset, light and camera previews. Saved landscape heightfield subset; no runtime spawning, foliage or streaming completeness, Unreal rendering parity or animation binding claimed.')
        text=bpy.data.texts.new(root.name+' - scene transfer.json');text.write(json.dumps(report,indent=2));root['UE_report']=text.name;root['UE_full_scene_source']=str(path);root['UE_preview_only']=True
        return root,report
    except Exception:
        scene.camera=old_camera;rollback_new(before);raise
