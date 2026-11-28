"""Build a Blender mesh from decoded source vertex-instance records.

The data contract is the independently validated MeshDescription representation;
mesh creation uses Blender's documented Python API and UE axis/unit conversion.
"""
def build_description(data, name, source):
    import bpy
    ids = sorted(data['vertices'])
    dense = {key: i for i,key in enumerate(ids)}
    def axis(v):
        return (v[1],v[0],v[2])
    positions = [tuple(c*.01 for c in axis(data['vertices'][key])) for key in ids]
    edges = [tuple(dense[v] for v in pair) for pair in data['edges'].values()]
    groups, corners = zip(*data['triangles'])
    faces = [tuple(dense[data['instances'][c]] for c in tri) for tri in corners]
    mesh = bpy.data.meshes.new(name)
    try:
        mesh.from_pydata(positions,edges,faces)
        if mesh.validate() or len(mesh.polygons)!=len(faces):
            raise ValueError('MeshDescription topology rejected')
        mesh.update()
        loop_ids = []
        for polygon,expected,tri in zip(mesh.polygons,faces,corners):
            if tuple(polygon.vertices)!=expected:
                raise ValueError('MeshDescription polygon order changed')
            polygon.use_smooth=True
            loop_ids.extend(tri)
        if len(loop_ids)!=len(mesh.loops):
            raise ValueError('MeshDescription loop count mismatch')
        def attribute(name,kind,domain,property_,values):
            attr=mesh.attributes.new(name,kind,domain)
            attr.data.foreach_set(property_,values)
        slot_ids=sorted(data['slots'])
        mesh['UE_material_slots']=[data['slots'][i] for i in slot_ids]
        mesh['UE_polygon_group_ids']=slot_ids
        mesh['UE_source_format']='Legacy FMeshDescription'
        mesh['UAsset']=str(source)
        attribute('UE_polygon_group','INT','FACE','value',groups)
        for number,channel in enumerate(data['uvs']):
            uv=mesh.uv_layers.new(name='UV'+str(number))
            uv.data.foreach_set('uv',[value for c in loop_ids for value in (channel[c][0],1-channel[c][1])])
        if data.get('colors') is not None:
            color=mesh.color_attributes.new(name='Color',type='FLOAT_COLOR',domain='CORNER')
            color.data.foreach_set('color',[v for c in loop_ids for v in data['colors'][c]])
        if data.get('tangents') is not None:
            attribute('UE_source_tangent','FLOAT_VECTOR','CORNER','vector',[v for c in loop_ids for v in axis(data['tangents'][c])])
        if data.get('signs') is not None:
            attribute('UE_source_binormal_sign','FLOAT','CORNER','value',[data['signs'][c][0] for c in loop_ids])
        if data.get('hard_edges') is not None:
            edge_flags={frozenset(dense[v] for v in data['edges'][i]):flag for i,flag in data['hard_edges'].items()}
            flags=[]
            for edge in mesh.edges:
                key=frozenset(edge.vertices)
                if key not in edge_flags: raise ValueError('MeshDescription edge identity missing')
                flag=edge_flags[key];flags.append(flag);edge.use_edge_sharp=flag
            attribute('UE_source_hard_edge','BOOLEAN','EDGE','value',flags)
        mesh.normals_split_custom_set([axis(data['normals'][c]) for c in loop_ids])
        return mesh
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
