"""Standalone cooked material dependency preview; no inferred shader bindings."""
from pathlib import Path
from project_paths import ProjectPaths
from cooked_material_dependencies import inspect_asset, recover_material_dependencies

PROFILES=('4.18','4.27','5.0')


def import_cooked_material(path,profile,allow_partial=False):
    import bpy
    from project_session import new_ids, rollback_new
    if profile not in PROFILES: raise NotImplementedError('Unsupported cooked material dependency profile')
    path=Path(path).resolve(); project=ProjectPaths(path); content=(Path(project.dir)/'Content').resolve()
    if project.descriptor is None or not path.is_relative_to(content):
        raise ValueError('Select a cooked material inside its original project Content directory')
    source='/Game/'+path.relative_to(content).with_suffix('').as_posix()
    if Path(project.resolve_package(source))!=path: raise ValueError('Invalid material package path')
    cls,_=inspect_asset(path,profile,source)
    if cls not in ('Material','MaterialInstanceConstant'): raise ValueError('Expected cooked material asset')
    before=set(new_ids())
    try:
        mat=bpy.data.materials.new(path.stem+' — cooked dependencies')
        mat['UE_material_package']=source
        mat['UE_cooked_profile']=profile
        mat['UE_editor_material_status']='cooked_dependencies_only'
        mat['UE_material_status']='shader_unresolved'
        mat.use_nodes=True
        # Do not present the default Principled shader as recovered source appearance.
        mat.node_tree.nodes.clear()
        records=recover_material_dependencies(mat,project,profile,source)
        if not records or records[0].get('class')!=cls: raise ValueError('Material dependency inventory failed')
        if profile=='4.18' and cls=='Material':
            import json
            from cooked_classic_material import read_source_edges
            try:
                graph=read_source_edges(path)
            except (ValueError,NotImplementedError,OSError) as exc:
                mat['UE_cooked_source_edge_issue']=str(exc)
            else:
                mat['UE_cooked_source_edges']=json.dumps(graph,sort_keys=True)
                for node in mat.node_tree.nodes:
                    if node.type!='TEX_IMAGE':continue
                    fields=[key for key,row in graph['edges'].items() if row['texture']==node.get('UE_texture_package')]
                    if fields:
                        node['UE_cooked_source_inputs']=json.dumps(fields)
                        node.label+=' → '+', '.join(fields)
                if allow_partial:
                    from cooked_material_preview import build_preview
                    build_preview(mat,project,graph)
        mat.use_fake_user=True
        return mat
    except Exception:
        rollback_new(before);raise
