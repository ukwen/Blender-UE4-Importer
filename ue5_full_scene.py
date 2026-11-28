"""One-operation native saved-level reconstruction, with explicit coverage and atomic ownership."""
import json
from pathlib import Path
from collections import Counter
from ue5_blueprint import read_tables, require
from ue5_editor_scene import external_packages


def actor_inventory(content, path, instance_records=None):
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
            if instance_records is not None:
                from ue5_instance_inventory import scan_exports
                instance_records.extend(scan_exports(exports,ref,pkg,rel,level,source==path))
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
        if obj.get('UE_brush_operand'):kind='brush_operand_guide'
        elif obj.get('UE_volume_guide'):kind='volume_guide'
        elif obj.type in ('MESH','ARMATURE'):kind='geometry'
        elif obj.type=='LIGHT':kind='light_preview'
        elif obj.type=='CAMERA':kind='camera_preview'
        elif obj.get('UE_decal_projector'):kind='decal_projector_guide'
        elif obj.get('UE_geometry_status') in ('missing','unsupported','failed'):kind='unresolved_geometry'
        else:kind='anchor_or_marker'
        statuses.setdefault(key,set()).add(kind)
    rows=[dict(r,representation=sorted(statuses.get((r['source'],r['actor']),{'not_reconstructed'}))) for r in inventory]
    counts=Counter(s for r in rows for s in r['representation'])
    return dict(serialized_level_exports=len(rows),representation_counts=dict(counts),records=rows,unrepresented_classes=dict(Counter(r['kind'] for r in rows if r['representation']==['not_reconstructed'])),scope='Counts overlap; markers and unresolved anchors are not reconstructed geometry. Direct saved level exports only, not runtime actors.')


def reconstruct(filepath,partial=False,preview_scale=1.,strict_dependencies=False,progress=None):
    iterator=iter_reconstruct(filepath,partial,preview_scale,strict_dependencies,progress=progress)
    try:
        while True:next(iterator)
    except StopIteration as done:return done.value
    finally:iterator.close()


def iter_reconstruct(filepath,partial=False,preview_scale=1.,strict_dependencies=False,cache_budget=None,progress=None):
    """Yield at safe boundaries; restore the caller cache context before every yield."""
    from import_workflow import _ACTIVE, TableCache, DEFAULT_BUDGET, Stages
    inherited=_ACTIVE.get();cache=inherited if inherited is not None else TableCache(DEFAULT_BUDGET if cache_budget is None else cache_budget)
    iterator=_reconstruct(filepath,partial,preview_scale,strict_dependencies,Stages(progress),cache)
    try:
        while True:
            token=_ACTIVE.set(cache)
            try:stage=next(iterator)
            except StopIteration as done:return done.value
            finally:_ACTIVE.reset(token)
            yield stage
    finally:
        iterator.close()
        if inherited is None:cache.items.clear();cache.resident=0


def _reconstruct(filepath,partial,preview_scale,strict_dependencies,stages_timer,cache):
    import bpy
    from mathutils import Matrix
    from uasset import UProject
    from project_session import new_ids,rollback_new
    from ue5_editor_scene import iter_geometry
    from ue5_editor_lighting import records as lights, reconstruct as lighting
    from ue5_editor_camera import records as cameras, reconstruct as camera
    path=Path(filepath).resolve();project=UProject(str(path));content=Path(project.dir)/'Content';scene=bpy.context.scene
    # Refuse overlapping independent imports too, rather than quietly duplicate or delete them.
    keys=('UE_full_scene_source','UE_source_map_path','UE_lighting_source','UE_camera_source')
    require(not any(str(path)==c.get(k) for c in scene.collection.children_recursive for k in keys),'Level already imported (full or separate stages); remove the prior import explicitly before retrying')
    from ue5_scene_dependencies import audit
    dependencies=stages_timer.run("Dependencies",audit,project,path)
    require(not strict_dependencies or dependencies['ready_for_strict_import'],
            f"Source dependency check failed: {dependencies['unresolved_hard']} hard, {dependencies['unresolved_soft_only']} soft-only unresolved, {len(dependencies['unknown_tables'])} unknown tables. Run Analyze Level Dependencies or disable strict mode.")
    yield "Dependencies complete"
    instance_records=[]
    inventory,errors=stages_timer.run("Actor inventory",actor_inventory,content,path,instance_records)
    yield "Actor inventory complete"
    from ue5_instance_inventory import summarize
    instance_report=summarize(instance_records,errors)
    from ue5_level_layout import inventory as layout_inventory
    try:layout=stages_timer.run("Level layout",layout_inventory,content,path)
    except ValueError as exc:layout=dict(status="unsupported",detail=str(exc))
    yield "Level layout complete"
    light_data=stages_timer.run("Light records",lights,content,path);camera_data=stages_timer.run("Camera records",cameras,content,path)
    yield "Light and camera records complete"
    before=set(new_ids());old_camera=scene.camera;old_world=scene.world
    try:
        root=bpy.data.collections.new('UE Scene — '+path.stem);scene.collection.children.link(root)
        def nest(c,name):
            root.children.link(c);scene.collection.children.unlink(c);c.name=name
        geom=iter_geometry(str(path),materials=True,components=True,partial=partial)
        try:
            while True:
                try:stage=stages_timer.run("Geometry and materials",next,geom)
                except StopIteration as done:geo,gr=done.value;break
                yield stage
        finally:geom.close()
        nest(geo,path.stem+' — Geometry and characters')
        yield 'Geometry and materials complete'
        stages={'geometry':gr};counts={'geometry_objects':len(geo.all_objects)}
        from ue5_editor_decals import extend_decals
        stages['decals']=stages_timer.run("Decals",extend_decals,content,path,root);counts['decal_objects']=stages['decals']['projector_anchors']+stages['decals']['size_guides']
        yield 'Decals complete'
        from ue5_editor_brushes import extend_brushes
        stages['brushes']=stages_timer.run("Brushes",extend_brushes,content,path,root);counts['brush_operand_objects']=stages['brushes']['operands']
        yield 'Brushes complete'
        from ue5_editor_bsp import extend_bsp
        stages['compiled_bsp']=stages_timer.run("Compiled BSP",extend_bsp,content,path,root,partial=partial);counts['compiled_bsp_objects']=stages['compiled_bsp']['components']
        yield 'Compiled BSP complete'
        from ue5_editor_volumes import extend_volumes
        stages['volumes']=stages_timer.run("Volumes",extend_volumes,content,path,root);counts['volume_guide_objects']=stages['volumes']['volumes']
        yield 'Volumes complete'
        for name,data,build in [('lighting',light_data,lambda:lighting(str(path),preview_scale)),('cameras',camera_data,lambda:camera(str(path)))]:
            if not data['records']:
                stages[name]=dict(data,status='no_supported_records');counts[name+'_objects']=0;continue
            c,r=stages_timer.run(name.title(),build);nest(c,path.stem+' — '+name.title());stages[name]=dict(r,status='preview');counts[name+'_objects']=len(c.all_objects)
            yield name.title()+' complete'
        from ue5_environment_preview import build as environment
        stages['environment']=stages_timer.run("Environment",environment,root,light_data['records'])
        from ue5_fog_preview import plan as fog_plan
        stages['environment']['fog_preview']=fog_plan(light_data['records'])
        yield 'Environment complete'
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
        require(scene.camera==old_camera and scene.world==old_world,'Unexpected active camera or world change')
        objects=list(root.all_objects);require(objects,'No supported scene objects reconstructed')
        material_counts=Counter(v['status'] for v in gr.get('material_report',{}).values())
        report=dict(source=str(path),status='bounded_scene_preview',stages=stages,counts=dict(counts,objects=len(objects),meshes=sum(o.type=='MESH' and not o.get('UE_brush_operand') and not o.get('UE_volume_guide') for o in objects),armatures=sum(o.type=='ARMATURE' for o in objects),lights=sum(o.type=='LIGHT' for o in objects),cameras=sum(o.type=='CAMERA' for o in objects)),coverage=coverage(inventory,objects),source_dependencies=dependencies,strict_dependencies=strict_dependencies,inventory_errors=errors,instance_inventory=instance_report,level_layout=layout,material_status=dict(material_counts),linked_character_cameras=linked,unlinked_character_cameras=unlinked,scope='Saved geometry, supported components, material subset, light and camera previews. Saved landscape heightfield subset and non-rendering decal guides and CSG brush operands; saved compiled BSP render polygon subset and non-rendering volume guides; opt-in analytical sky where supported; opt-in finite fog preview separately available; no Unreal fog equivalence, runtime spawning, foliage or streaming completeness, Unreal rendering parity or animation binding claimed.')
        from material_gap_diagnostics import material_gaps
        scene_materials=[(r.get('material_package'),'decal_projector') for r in stages['decals']['records']]
        scene_materials.extend((r.get('material_package'),'landscape_surface') for r in gr['landscape_report']['records'])
        report["material_diagnostics"]=material_gaps(gr.get("material_report",{}),dependencies,scene_materials)
        report["performance"]=dict(stages_timer.report(),**cache.stats())
        report["performance"]["scope"]="Stage timings measure synchronous work; elapsed includes modal pauses and excludes final report serialization. Cancellation occurs only between stages or batches."
        text=bpy.data.texts.new(root.name+' - scene transfer.json');text.write(json.dumps(report,indent=2));root['UE_report']=text.name;root['UE_full_scene_source']=str(path);root['UE_preview_only']=True
        return root,report
    except BaseException:
        scene.camera=old_camera;scene.world=old_world;rollback_new(before);raise
