"""Recover typed cooked material dependencies and packed raw image data.
Import-table dependencies are not shader input assignments. No graph inference.
"""
import json
from pathlib import Path
from skeletal_mesh_native import require


def inspect_asset(path,profile,expected):
    if profile in ('4.18','4.27'):
        from project_geometry import read_ue4_split_tables
        cls,name,names,imports,_=read_ue4_split_tables(path)
        require(name==expected.rsplit('/',1)[-1] and expected in names,'UE4 root name/package evidence mismatch')
    elif profile=='5.0':
        from ue5_cooked_geometry import package
        cls,name,names,imports,_=package(path)
        require(name==expected.rsplit('/',1)[-1] and expected in names,'UE5.0 root name/package evidence mismatch')
    else:
        from ue5_modern_static import package
        cls,name,_,imports,_,source=package(path)
        require(source==expected and name==expected.rsplit('/',1)[-1],'Serialized package identity mismatch')
    return cls,imports


def texture_references(imports):
    result=set()
    for imp in imports:
        if imp[1]!='Texture2D' or imp[3].startswith('Default__'): continue
        outer=imp[2]
        require(-len(imports)<=outer<0 and imports[-outer-1][1]=='Package','Invalid texture import outer')
        package=imports[-outer-1][3]
        require(package.startswith(('/Game/','/Engine/')) and package.rsplit('/',1)[-1]==imp[3],'Unsupported texture import identity')
        result.add(package)
    return sorted(result)


def pack_texture(project,source,profile):
    import bpy
    from project_session import hash_file,digest
    from texture_blender import load_native_texture
    path=Path(project.resolve_package(source))
    if not path.is_file(): raise FileNotFoundError('Texture source package unavailable')
    cls,_=inspect_asset(path,profile,source);require(cls=='Texture2D','Referenced package is not a Texture2D')
    if profile not in ('4.18','4.27','5.0','5.5'): raise NotImplementedError('Texture decoder unavailable for this cooked profile')
    files=[path]+[path.with_suffix(e) for e in ('.uexp','.ubulk','.uptnl') if path.with_suffix(e).is_file()]
    require(all(p.stat().st_size<=128*1024*1024 for p in files),'Texture source exceeds size limit')
    key=digest([profile,source,[(str(p),hash_file(p)) for p in files]])
    for image in bpy.data.images:
        if image.get('UE_raw_texture_key')==key and image.packed_file and image.colorspace_settings.name=='Non-Color': return image
    # No shader/sRGB/normal semantics are asserted by the import table.
    image=load_native_texture(path,profile,srgb=False,normal=False)
    image['UE_raw_texture_key']=key;image['UE_texture_package']=source;image['UE_texture_semantics']='raw decoded channels; shader and color interpretation unresolved'
    return image


def recover_material_dependencies(material,project,profile,source):
    """Read exact direct and parent references, preserving scope and reporting missing data."""
    from ue5_cooked_material import read_instance
    records=[];visited=set();current=source;depth=0
    while current:
        if current in visited or depth>=32:
            records.append(dict(package=current,status='blocked_cycle_or_depth'));break
        visited.add(current);depth+=1
        record=dict(package=current,status='unresolved',textures=[])
        records.append(record)
        try:
            path=Path(project.resolve_package(current))
            if not path.is_file(): raise FileNotFoundError('Material source package unavailable')
            cls,imports=inspect_asset(path,profile,current)
            require(cls in ('Material','MaterialInstanceConstant'),'Invalid material dependency class')
            record['class']=cls;refs=texture_references(imports)
            record['status']='typed_references_recovered'
            current=read_instance(path,profile)['parent'] if cls=='MaterialInstanceConstant' else None
        except (OSError,ValueError,NotImplementedError) as exc:
            record['detail']=str(exc);break
        for ref in refs:
            item=dict(package=ref,status='unresolved');record['textures'].append(item)
            try:
                image=pack_texture(project,ref,profile);item.update(status='packed_raw_channels',image=image.name)
            except (OSError,ValueError,NotImplementedError) as exc: item['detail']=str(exc)
    material['UE_cooked_material_dependencies']=json.dumps(records,sort_keys=True)
    material['UE_unresolved_material']=True;material.use_nodes=True
    nodes=material.node_tree.nodes
    frame=nodes.new('NodeFrame');frame.label='Source texture dependencies — shader inputs unresolved';frame.location=(-1000,0)
    # Preserve dependency scope. Exact instance-parameter nodes can receive an
    # image, but parent references are not substituted into instance parameters.
    i=0
    for record in records:
        for item in record.get('textures',[]):
            ref=item['package'];matching=[n for n in nodes if n.get('UE_parameter_identity') and n.get('UE_texture_package')==ref] if record['package']==source else []
            if not matching:
                n=nodes.new('ShaderNodeTexImage');n.parent=frame;n.location=(0,-250*i);i+=1
                n.label=ref.rsplit('/',1)[-1]+' (dependency only)';n['UE_texture_package']=ref;n['UE_dependency_material']=record['package'];matching=[n]
            for n in matching:
                n['UE_texture_dependency_status']=item['status']
                if item['status']=='packed_raw_channels':
                    import bpy
                    n.image=bpy.data.images[item['image']]
                    n.label=n.label.replace(' (source texture unresolved)','')+' (raw channels)'
    return records
