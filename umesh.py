import os, io, sys, math, uuid, bpy, bmesh, importlib, time, struct, zlib
from ctypes import *
from mathutils import Vector, Matrix
from bpy.props import *
from bpy_extras.io_utils import ImportHelper

cur_dir = os.path.dirname(__file__)
if cur_dir not in sys.path: sys.path.append(cur_dir)
import uasset, umat, addon_lifecycle
from mesh_description import decode_mesh_description
from uasset import UAsset, Export, FStripDataFlags, FVector, FVector4, FVector2D, FColor, Euler, PrintableStruct
from umat import TryGetUMaterialImport

def uint16_to_float(value:c_uint16):
    sign = (value >> 15) & 0b0000000000000001
    exp  = (value >> 10) & 0b0000000000011111
    mant =  value        & 0b0000001111111111
    exp  = exp + (127 - 15)
    return struct.unpack('<f', struct.pack('<I', (sign << 31) | (exp << 23) | (mant << 13)))[0]

class FApexClothPhysToRenderVertData(PrintableStruct): _fields_ = ( ('pos_bary_d', FVector4), ('normal_bary_d', FVector4), ('tang_bary_d', FVector4), ('simul_mesh_vert_inds', c_int16 * 4), ('pad', c_int32 * 2) )
class FPackedNormal(PrintableStruct):
    _fields_ = ( ('packed', c_uint32), )
    def Unpack(self):
        # TODO: Handle 4.20: ^ 0b10000000100000001000000010000000 # offset by 128
        return ( # Y, X, Z
            ((self.packed >> 8 ) & 0xFF) / 127.5 - 1,
            ( self.packed        & 0xFF) / 127.5 - 1,
            ((self.packed >> 16) & 0xFF) / 127.5 - 1
        )
class FMeshUVHalf(PrintableStruct):
    _fields_ = ( ('u', c_uint16), ('v', c_uint16) )
    def ToFloat2(self): return (uint16_to_float(self.u), 1 - uint16_to_float(self.v))
class BulkHeader:
    def Read(self, f:uasset.ByteStream, summary:uasset.USummary):
        self.flags = f.ReadUInt32()
        b64 = self.flags & 0x2000 # Size64Bit
        assert not b64
        self.count = f.ReadUInt64() if b64 else f.ReadUInt32()
        self.byte_size = f.ReadUInt64() if b64 else f.ReadUInt32()
        self.offset = f.ReadInt32() if summary.version_ue4 < 198 else f.ReadInt64()
        if not (self.flags & 0x10000): self.offset += summary.bulk_data_offset # NoOffsetFixUp
        return self

v_obj_guid     = uuid.UUID('E4B068ED-42E9-F494-0BDA-31A241BB462E') # 0xE4B068ED, 0xF49442E9, 0xA231DA0B, 0x2E46BB41
v_ent_obj_guid = uuid.UUID('9DFFBCD6-0158-494F-8212-21E288A8923C') # 0x9DFFBCD6, 0x494F0158, 0xE2211282, 0x3C92A888
v_tang_guid    = uuid.UUID('5579F886-4C1F-933A-7B08-BA832FB96163') # 
v_ren_guid     = uuid.UUID('12F88B9F-4AFC-8875-0CD9-7CA629BD3A38') # 0x12F88B9F, 0x88754AFC, 0xA67CD90C, 0x383ABD29
v_skel_guid    = uuid.UUID('D78A4A00-4697-E858-B519-A8BAB4467D48') # 0xD78A4A00, 0xE8584697, 0xBAA819B5, 0x487D46B4

def ReadStripFlags(f:uasset.ByteStream, summary:uasset.USummary, min_v = 130) -> FStripDataFlags: return f.ReadStructure(FStripDataFlags) if summary.version_ue4 >= min_v else FStripDataFlags()
def ReadFMultisizeIndexContainer(f:uasset.ByteStream, summary:uasset.USummary):
    if summary.version_ue4 < 283: need_cpu_access = f.ReadBool32() # VER_UE4_KEEP_SKEL_MESH_INDEX_DATA
    size = f.ReadUInt8()
    return f.ReadBulkArray(c_uint16 if size == 2 else c_uint32)
def DecodeCompressedRawMesh(payload, expected_size):
    """Unreal SerializeCompressed, 64-bit little-endian chunk table, zlib only."""
    max_size = 256 * 1024 * 1024
    if not 0 < expected_size <= max_size or len(payload) < 32:
        raise ValueError("Invalid compressed raw mesh size")
    magic, block_size, compressed_size, total_size = struct.unpack_from('<QQQQ', payload)
    if magic != 0x9E2A83C1 or not 0 < block_size <= max_size or total_size != expected_size:
        raise ValueError("Invalid Unreal compressed raw mesh header")
    blocks = (total_size + block_size - 1) // block_size
    table_end = 32 + 16 * blocks
    if table_end > len(payload) or compressed_size != len(payload) - table_end:
        raise ValueError("Invalid compressed chunk table length")
    result = bytearray()
    offset = table_end
    for i in range(blocks):
        packed, unpacked = struct.unpack_from('<QQ', payload, 32 + i * 16)
        expected = min(block_size, total_size - len(result))
        if unpacked != expected or not packed or packed > len(payload) - offset:
            raise ValueError("Invalid compressed chunk size")
        decoder = zlib.decompressobj()
        data = decoder.decompress(payload[offset:offset+packed], expected + 1)
        if len(data) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("Invalid zlib chunk")
        result.extend(data)
        offset += packed
    if offset != len(payload) or len(result) != total_size:
        raise ValueError("Compressed mesh size mismatch")
    return bytes(result)


def ReadMeshBulkData(self:Export, asset:UAsset, f:uasset.ByteStream):
    bulk = BulkHeader().Read(f, asset.summary)
    if bulk.flags & 0x20 or bulk.count == 0: return None
    if bulk.flags & (0x100 | 0x800): raise NotImplementedError("Separate or optional bulk payload")
    if not bulk.flags & 1: raise NotImplementedError("Non-external raw mesh bulk payload")
    if bulk.flags & (0x10 | 0x80) or asset.summary.compression_flags:
        raise NotImplementedError("Non-zlib mesh compression")
    if not 0 < bulk.byte_size <= 256 * 1024 * 1024 or bulk.offset < 0:
        raise ValueError("Invalid mesh bulk range")
    pos = f.Position()
    try:
        f.Seek(0, io.SEEK_END)
        if bulk.offset + bulk.byte_size > f.Position(): raise ValueError("Mesh bulk outside package")
        f.Seek(bulk.offset)
        payload = f.ReadBytes(bulk.byte_size)
        if bulk.flags & 2: payload = DecodeCompressedRawMesh(payload, bulk.count)
        elif len(payload) != bulk.count: raise ValueError("Raw mesh bulk size mismatch")
        if asset.summary.custom_versions.get(v_obj_guid, 0) >= 28:
            return BuildMeshDescription(self, decode_mesh_description(payload))
        return DecodeRawMesh(self, asset, uasset.ByteStream(io.BytesIO(payload)))
    finally:
        f.Seek(pos)


def BuildMeshDescription(export, data):
    # UE uses left-handed winding; swapping X/Y reflects it into Blender space.
    vertex_ids = sorted(data['vertices'])
    index = {v: i for i,v in enumerate(vertex_ids)}
    verts = [(y*.01, x*.01, z*.01) for x,y,z in (data['vertices'][v] for v in vertex_ids)]
    triangles = data['triangles']
    faces = [tuple(index[data['instances'][c]] for c in corners) for _,corners in triangles]
    mesh = bpy.data.meshes.new(export.object_name)
    try:
        mesh.from_pydata(verts, [tuple(index[v] for v in edge) for edge in data['edges'].values()], faces)
        if mesh.validate(verbose=False): raise ValueError('Blender rejected source topology')
        mesh.update()
        if len(mesh.polygons) != len(triangles): raise ValueError('Triangle count mismatch')
        slot_ids = sorted(data['slots'])
        mesh['UE_material_slots'] = [data['slots'][g] for g in slot_ids]
        group_attr = mesh.attributes.new('UE_polygon_group', 'INT', 'FACE')
        group_attr.data.foreach_set('value', [g for g,_ in triangles])
        mesh['UE_polygon_group_ids'] = slot_ids
        mesh['UE_source_format'] = 'Legacy FMeshDescription'
        mesh['UAsset'] = export.asset.f.byte_stream.name
        loop_instances = []
        for poly,(group,corners) in zip(mesh.polygons,triangles):
            if tuple(poly.vertices) != tuple(index[data['instances'][c]] for c in corners):
                raise ValueError('Unexpected Blender polygon order')
            poly.use_smooth = True
            loop_instances.extend(corners)
        for channel,values in enumerate(data['uvs']):
            uv = mesh.uv_layers.new(name=f'UV{channel}')
            uv.data.foreach_set('uv', [x for c in loop_instances for x in (values[c][0],1-values[c][1])])
        if data['colors'] is not None:
            color = mesh.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER')
            color.data.foreach_set('color',[x for c in loop_instances for x in data['colors'][c]])
        if data.get('tangents') is not None:
            attr = mesh.attributes.new('UE_source_tangent', 'FLOAT_VECTOR', 'CORNER')
            attr.data.foreach_set('vector', [v for c in loop_instances for v in (data['tangents'][c][1],data['tangents'][c][0],data['tangents'][c][2])])
        if data.get('signs') is not None:
            attr = mesh.attributes.new('UE_source_binormal_sign', 'FLOAT', 'CORNER')
            attr.data.foreach_set('value', [data['signs'][c][0] for c in loop_instances])
        if data.get('hard_edges') is not None:
            hard = {tuple(sorted(index[v] for v in data['edges'][i])):flag for i,flag in data['hard_edges'].items()}
            if any(tuple(sorted(e.vertices)) not in hard for e in mesh.edges):
                raise ValueError('MeshDescription edge topology mismatch')
            attr = mesh.attributes.new('UE_source_hard_edge', 'BOOLEAN', 'EDGE')
            attr.data.foreach_set('value', [hard[tuple(sorted(e.vertices))] for e in mesh.edges])
            for edge in mesh.edges: edge.use_edge_sharp = hard[tuple(sorted(edge.vertices))]
        mesh.normals_split_custom_set([(y,x,z) for x,y,z in (data['normals'][c] for c in loop_instances)])
        return mesh
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise


def DecodeRawMesh(self, asset, f):
    # FRawMesh
    version, version_licensee = (f.ReadInt32(), f.ReadInt32())
    if version not in (0, 1) or version_licensee != 0:
        raise NotImplementedError(f"Unsupported mesh payload layout ({version}, {version_licensee}); FMeshDescription decoder required")
    face_mat_indices:list[c_int32] = f.ReadArray(c_int32)
    f.SkipArray(c_uint32)#face_smoothing_mask = f.ReadArray(c_uint32)
    vertices:list[FVector] = f.ReadArray(FVector)
    wedge_indices = f.ReadArray(c_int32)
    f.SkipArray(FVector)#wedge_tangents = f.ReadArray(FVector)
    f.SkipArray(FVector)#wedge_binormals = f.ReadArray(FVector)
    wedge_normals:list[FVector] = f.ReadArray(FVector)
    wedge_uvs:list[list[FVector2D]] = []
    for i_uv in range(8): wedge_uvs.append(f.ReadArray(FVector2D))
    wedge_colors:list[FColor] = f.ReadArray(FColor)
    if version >= 1: mat_index_to_import_index = f.ReadArray(c_int32)

    bmsh = bmesh.new()
    for pos in vertices: bmsh.verts.new(Vector((pos.y, pos.x, pos.z)))
    bmsh.verts.ensure_lookup_table()
    
    uvs = []
    for i_uv in range(len(wedge_uvs)):
        if len(wedge_uvs[i_uv]) > 0: uvs.append((i_uv, bmsh.loops.layers.uv.new(f"UV{i_uv}")))
    
    has_normals = len(wedge_normals) > 0
    has_colors = len(wedge_colors) > 0
    if has_colors: col_lay = bmsh.loops.layers.color.new("Color")
    
    spl_norms = []
    for i_wedge in range(0, len(wedge_indices), 3):
        try:
            face = bmsh.faces.new((
                bmsh.verts[wedge_indices[i_wedge+0]],
                bmsh.verts[wedge_indices[i_wedge+1]],
                bmsh.verts[wedge_indices[i_wedge+2]]
            ))
            loops = face.loops
            i_poly = int(i_wedge / 3)
            #face.smooth = face_smoothing_mask[i_poly] == 0
            face.material_index = face_mat_indices[i_poly]

            if has_normals:
                n1 = wedge_normals[i_wedge + 0]
                n2 = wedge_normals[i_wedge + 1]
                n3 = wedge_normals[i_wedge + 2]
                spl_norms.append(Vector((n1.y, n1.x, n1.z)))
                spl_norms.append(Vector((n2.y, n2.x, n2.z)))
                spl_norms.append(Vector((n3.y, n3.x, n3.z)))
            if has_colors:
                col1 = wedge_colors[i_wedge + 0]
                col2 = wedge_colors[i_wedge + 1]
                col3 = wedge_colors[i_wedge + 2]
                loops[0][col_lay] = Vector((col1.r,col1.g,col1.b,col1.a)) / 255.0
                loops[1][col_lay] = Vector((col2.r,col2.g,col2.b,col2.a)) / 255.0
                loops[2][col_lay] = Vector((col3.r,col3.g,col3.b,col3.a)) / 255.0

            for i_uv, uv_layer in uvs:
                uv1 = wedge_uvs[i_uv][i_wedge + 0]
                uv2 = wedge_uvs[i_uv][i_wedge + 1]
                uv3 = wedge_uvs[i_uv][i_wedge + 2]
                loops[0][uv_layer].uv = (uv1.x, 1-uv1.y)
                loops[1][uv_layer].uv = (uv2.x, 1-uv2.y)
                loops[2][uv_layer].uv = (uv3.x, 1-uv3.y)
        except ValueError: pass # Face already exists

    mesh = bpy.data.meshes.new(self.object_name)
    mesh.name = self.object_name
    bmsh.to_mesh(mesh)
    bmsh.free()
    if has_normals: mesh.normals_split_custom_set(spl_norms)
    if hasattr(mesh, 'use_auto_smooth'):
        mesh.use_auto_smooth = True
    mesh.transform(Matrix.Identity(4) * 0.01)
    mesh["UAsset"] = self.asset.f.byte_stream.name
    # TODO: flip_normals() faster?

    return mesh
def ReadFSkelMeshVertexBase(f:uasset.ByteStream, v_ren):
    pos = f.ReadStructure(FVector)
    if v_ren < 26: packed_normals = f.ReadStructure(FPackedNormal * 3) # IncreaseNormalPrecision
    else: new_nx, new_ny, new_nz = (f.ReadStructure(FVector), f.ReadStructure(FVector), f.ReadStructure(FVector4))
def ImportStaticMesh(self:Export, import_materials=True, log=True, all_lods=False):
    """Import explicit editor source LODs; generated/cooked LODs are not invented."""
    existing = {m.as_pointer() for m in bpy.data.meshes}
    try:
        return _ImportStaticMesh(self, import_materials, log, all_lods)
    except Exception:
        for candidate in list(bpy.data.meshes):
            if candidate.as_pointer() not in existing and candidate.users == 0:
                bpy.data.meshes.remove(candidate)
        raise


def _ImportStaticMesh(self, import_materials, log, all_lods):
    import json
    t0 = time.time()
    asset = self.asset
    if asset.summary.version_ue4 == 508:
        from legacy_static import import_legacy_static
        return import_legacy_static(self, import_materials, all_lods)
    f = asset.f
    self.ReadProperties(False, False)
    if f.ReadInt32(): self.guid = f.ReadGuid()
    strip_flags = ReadStripFlags(f, asset.summary)
    cooked = f.ReadBool32()
    asset.DecodePackageIndex(f.ReadInt32()) # BodySetup
    if asset.summary.version_ue4 >= 216: asset.DecodePackageIndex(f.ReadInt32()) # NavCollision
    if cooked or strip_flags.StripForEditor():
        raise NotImplementedError('Cooked or editor-stripped static mesh')
    if asset.summary.version_ue4 < 242:
        raise NotImplementedError('Unsupported static mesh editor header')
    f.ReadFString(); f.ReadUInt32() # high-resolution source name, CRC
    f.ReadGuid() # lighting GUID
    socket_count = f.ReadInt32()
    if not 0 <= socket_count <= 1024: raise ValueError('Invalid socket count')
    sockets = [asset.DecodePackageIndex(f.ReadInt32()) for _ in range(socket_count)]
    socket_names = [ref.object_name if ref is not None else None for ref in sockets]
    v_obj = asset.summary.custom_versions.get(v_obj_guid, 0)
    editor = not (asset.summary.package_flags & 0x8)
    source_models = self.properties.TryGetValue('SourceModels', [])
    if not 1 <= len(source_models) <= 64: raise ValueError('Invalid source LOD count')
    meshes = []
    missing_lods = []
    for lod_index, src_model in enumerate(source_models):
        lod_mesh = None
        if v_obj < 28:
            lod_mesh = ReadMeshBulkData(self, asset, f)
            f.ReadGuid(); f.ReadBool32()
        elif f.ReadBool32():
            lod_mesh = ReadMeshBulkData(self, asset, f)
            if v_obj >= 29: f.ReadGuid()
            if asset.summary.custom_versions.get(v_ent_obj_guid, 0) >= 8: f.ReadBool32()
        if lod_mesh is None:
            missing_lods.append(lod_index)
        else:
            lod_mesh['UE_lod_index'] = lod_index
            meshes.append(lod_mesh)
    if not meshes: raise NotImplementedError('No supported editor source mesh')
    primary = meshes[0]
    if not all_lods:
        for lod_mesh in meshes[1:]: bpy.data.meshes.remove(lod_mesh)
        meshes = [primary]
    ue4_v = asset.summary.compatible_version
    ue4_14_or_above = ue4_v.major >= 4 and ue4_v.minor >= 14
    if ue4_14_or_above:
        if f.ReadBool32(): raise NotImplementedError('SpeedTree wind serialization')
        if v_obj >= 8:
            source_slots, source_packages, interfaces, display_names = [], [], [], []
            slot_count = f.ReadInt32()
            if not 0 <= slot_count <= 4096: raise ValueError('Invalid static material count')
            for _ in range(slot_count):
                mat_interface, mat_slot_name = (asset.DecodePackageIndex(f.ReadInt32()), f.ReadFName(asset.names))
                imported_mat_slot_name = f.ReadFName(asset.names) if editor else mat_slot_name
                if v_obj >= 10:
                    f.ReadBool32(); f.ReadBool32()
                    for _ in range(4): f.ReadFloat()
                from material_stage import package_reference
                source_slots.append(imported_mat_slot_name)
                source_packages.append(package_reference(mat_interface))
                interfaces.append(mat_interface); display_names.append(mat_slot_name)
            for mesh in meshes:
                mesh['UE_material_bindings'] = json.dumps(list(zip(source_slots, source_packages)))
                mesh['UE_static_material_slots'] = source_slots
                if mesh.get('UE_source_format') == 'Legacy FMeshDescription':
                    names = list(mesh['UE_material_slots']); ids = list(mesh['UE_polygon_group_ids'])
                    mapping = {g:source_slots.index(n) for g,n in zip(ids,names) if source_slots.count(n)==1}
                    if len(mapping)!=len(ids):
                        mesh['UE_material_binding_error'] = 'MeshDescription material slot mapping is ambiguous or missing'
                        if import_materials: raise ValueError(mesh['UE_material_binding_error'])
                    else:
                        indices = [mapping[entry.value] for entry in mesh.attributes['UE_polygon_group'].data]
                        attr = mesh.attributes.new('UE_source_material_index', 'INT', 'FACE')
                        attr.data.foreach_set('value',indices)
            if import_materials:
                materials = []
                for ref,name in zip(interfaces,display_names):
                    mat = TryGetUMaterialImport(ref, mesh=primary) if ref else None
                    if mat is None:
                        mat = bpy.data.materials.new(name); mat['UE_unresolved_material'] = True
                    materials.append(mat)
                for mesh in meshes:
                    for mat in materials: mesh.materials.append(mat)
                    attr = mesh.attributes.get('UE_source_material_index')
                    if attr is not None:
                        for poly,entry in zip(mesh.polygons,attr.data): poly.material_index = entry.value
    elif import_materials:
        materials = [TryGetUMaterialImport(p.value,mesh=primary) for p in self.properties.TryGetValue('Materials',[])]
        for mesh in meshes:
            for mat in materials: mesh.materials.append(mat)
    for mesh in meshes:
        mesh['UE_source_lod_count'] = len(source_models)
        mesh['UE_missing_source_lods'] = json.dumps(missing_lods)
        mesh['UE_socket_references'] = json.dumps(socket_names)
        if all_lods: mesh.name = f"{self.object_name}_LOD{mesh['UE_lod_index']}"
        if log: print(f"Imported {mesh.name} ({len(mesh.vertices)} Verts, {len(mesh.polygons)} Tris): {(time.time()-t0)*1000:.2f}ms")
    return meshes if all_lods else primary

def ImportSkeletalMesh(self:Export, import_materials=True, o=None):
    asset = self.asset
    f = asset.f
    collection = bpy.context.collection
    self.ReadProperties(False, False)

    '''if sk := self.properties.TryGetValue('Skeleton'):
        armature = bpy.data.armatures.new(sk.object_name)
        armature_obj = bpy.data.objects.new(armature.name, armature)
        collection.objects.link(armature_obj)'''

    if f.ReadInt32(): self.guid = f.ReadGuid()

    strip_flags = ReadStripFlags(f, asset.summary)
    bounds = f.ReadStructure(uasset.FBoxSphereBounds)

    v_obj = asset.summary.custom_versions.get(v_obj_guid, 0)
    v_tangent = asset.summary.custom_versions.get(v_tang_guid, 0)
    v_ren = asset.summary.custom_versions.get(v_ren_guid, 0)
    v_skel = asset.summary.custom_versions.get(v_skel_guid, 0)

    bmsh = bmesh.new()

    # TArray<FSkeletalMaterial> Materials;
    materials = []
    for i in range(f.ReadInt32()):
        mat_import = asset.DecodePackageIndex(f.ReadInt32())
        materials.append(mat_import)
        assert v_obj < 8 # RefactorMeshEditorMaterials
        if asset.summary.version_ue4 >= 302: shadow_casting = f.ReadBool32() # VER_UE4_MOVE_SKELETALMESH_SHADOWCASTING
        if v_tangent >= 1: recompute_tangent = f.ReadBool32() # RuntimeRecomputeTangent
        assert v_ren < 10 # TextureStreamingMeshUVChannelData

    # FReferenceSkeleton
    #ref_bone_info = # TArray<FMeshBoneInfo>
    ref_bone_info = []
    for i in range(f.ReadInt32()):
        name, i_parent = (f.ReadFName(asset.names), f.ReadInt32())
        assert i_parent >= -1
        if asset.summary.version_ue4 < 310: color = f.ReadStructure(FColor) # VER_UE4_REFERENCE_SKELETON_REFACTOR
        if asset.summary.version_ue4 >= 370: export_name = f.ReadFString() # VER_UE4_STORE_BONE_EXPORT_NAMES
        ref_bone_info.append((name, i_parent))

    ref_bone_pose:list[uasset.FTransform] = f.ReadArray(uasset.FTransform) # TArray<FTransform>

    '''bpy.context.view_layer.objects.active = armature_obj
    armature_obj.select_set(True)
    armature.show_names = True
    armature_obj.show_in_front = True
    bpy.ops.object.mode_set(mode='EDIT')
    for i in range(len(ref_bone_info)) :
        name, i_parent = ref_bone_info[i]
        bone = armature.edit_bones.new(name)
        transform = ref_bone_pose[i]

        euler = transform.rotation.ToEuler()
        #euler = Euler((0,0,0), 'YXZ')
        euler = Euler((-euler.x, -euler.z, -euler.y), 'YXZ')
        print(f"{i} {name} {euler}")

        #bone.head = transform.translation.ToVectorPos() * 0.01
        #bone.head = transform.translation.ToVector() * 0.01
        #bone.tail = bone.head + Vector((0, 0, 0.1))

        matrix = Matrix.LocRotScale(transform.translation.ToVectorPos() * 0.01, euler, transform.scale.ToVector())
        #bone.head = matrix @ Vector((0,0,0))
        #bone.tail = matrix @ Vector((0.01,0,0))

        if i_parent != -1:
            bone.parent = armature.edit_bones[i_parent]
            #matrix = matrix @ bone.parent.matrix
            matrix = bone.parent.matrix @ matrix

        bone.head = (0,0,0)
        bone.tail = (0.01,0,0)
        #bone.tail = (0,0.01,0)
        bone.matrix = matrix
    bpy.ops.object.mode_set(mode='OBJECT')'''
    
    index_to_name = {}
    if asset.summary.version_ue4 >= 310: # VER_UE4_REFERENCE_SKELETON_REFACTOR
        for i in range(f.ReadInt32()):
            key, value = ( f.ReadFName(asset.names), f.ReadInt32() )
            index_to_name[value] = key
            #print(f"{value} {key}")
    else:
        for i in range(len(ref_bone_info)): index_to_name[i] = ref_bone_info[i][0]

    mesh = bpy.data.meshes.new(self.object_name) # TODO: oy vey, static mesh doesn't have to create an object
    mesh.name = self.object_name
    o = bpy.data.objects.new(mesh.name, mesh)
    collection.objects.link(o)

    #modifier = o.modifiers.new("Skeleton", 'ARMATURE')
    #modifier.object = armature_obj

    bone_groups:list[bpy.types.VertexGroup] = []
    for i in sorted(index_to_name): bone_groups.append(o.vertex_groups.new(name=index_to_name[i]))
    
    if v_skel < 12: # SplitModelAndRenderData
        # lods = 
        for i_lod in range(f.ReadInt32()):
            # FStaticLODModel4
            lod_strip_flags = ReadStripFlags(f, asset.summary)

            has_cloth_data = False

            # FSkelMeshSection4 sections
            sections = []
            for i_sect in range(f.ReadInt32()):
                sect_strip_flags = ReadStripFlags(f, asset.summary)
                strip_server = sect_strip_flags.StripForServer()
                i_mat = f.ReadInt16()
                if v_skel < 1: i_chunk = f.ReadInt16() # CombineSectionWithChunk
                if not strip_server:
                    i_base, tri_count = (f.ReadInt32(), f.ReadInt32())
                    sections.append((i_mat, i_base, tri_count))
                if v_skel < 13: tri_sorting = f.ReadUInt8() # RemoveTriangleSorting
                if asset.summary.version_ue4 >= 254: # VER_UE4_APEX_CLOTH
                    if v_skel < 15: disabled = f.ReadBool32() # DeprecateSectionDisabledFlag
                    if v_skel < 14: cloth_section = f.ReadInt16() # RemoveDuplicatedClothingSections
                if asset.summary.version_ue4 >= 280: enable_cloth_lod_depricated = f.ReadUInt8() # VER_UE4_APEX_CLOTH_LOD
                if v_tangent >= 1: recompute_tangent = f.ReadBool32() # RuntimeRecomputeTangent
                if v_tangent >= 2: recompute_tangent_vert_mask_channel = f.ReadUInt8() # RecomputeTangentVertexColorMask
                if v_obj >= 8: cast_shadow = f.ReadBool32() # RefactorMeshEditorMaterials
                if v_skel >= 1: # CombineSectionWithChunk
                    if not strip_server: i_base_vert = f.ReadUInt32()
                    if not sect_strip_flags.StripForEditor(): # TODO
                        if v_skel < 2: raise # CombineSoftAndRigidVerts
                        raise
                    raise
            
            if v_skel < 12: indices = ReadFMultisizeIndexContainer(f, asset.summary) # SplitModelAndRenderData
            else: indices = f.ReadArray(c_uint32)
            
            active_bone_indices = f.ReadArray(c_int16) # Bones with vertices

            assert not (asset.summary.compatible_version.major >= 4 and asset.summary.compatible_version.minor >= 20), "Handle packed normals"

            chunks = None
            if v_skel < 1: # CombineSectionWithChunk
                # TArray<FSkelMeshChunk4> Chunks
                chunks = []
                for i_chunk in range(f.ReadInt32()):
                    strip_flags = ReadStripFlags(f, asset.summary)
                    if not strip_flags.StripForServer(): base_vert_i = f.ReadInt32()
                    if not strip_flags.StripForEditor():
                        skel_influences = 8 if asset.summary.version_ue4 >= 332 else 4 # VER_UE4_SUPPORT_8_BONE_INFLUENCES_SKELETAL_MESHES
                        # FRigidVertex4 rigid_verts
                        for i in range(f.ReadInt32()):
                            ReadFSkelMeshVertexBase(f, v_ren)
                            uvs, color, i_bone = (f.ReadStructure(FVector2D * 4), f.ReadStructure(FColor), f.ReadUInt8())
                        # FSoftVertex4 soft_verts
                        for i in range(f.ReadInt32()):
                            ReadFSkelMeshVertexBase(f, v_ren)
                            uvs, color = (f.ReadStructure(FVector2D * 4), f.ReadStructure(FColor))
                            assert skel_influences > 4 and skel_influences <= 8
                            bone_indices = f.ReadStructure(c_ubyte * skel_influences)
                            bone_weights = f.ReadStructure(c_ubyte * skel_influences)
                    bone_map, rigid_vert_c, soft_vert_c, max_bone_influences = (f.ReadArray(c_uint16), f.ReadInt32(), f.ReadInt32(), f.ReadInt32())
                    if asset.summary.version_ue4 >= 254: # VER_UE4_APEX_CLOTH
                        cloth_mappings, physical_mesh_verts, physical_mesh_norms = (f.ReadArray(FApexClothPhysToRenderVertData), f.ReadArray(FVector), f.ReadArray(FVector))
                        cloth_asset_i, cloth_submesh_i = (f.ReadInt16(), f.ReadInt16())
                        has_cloth_data |= len(cloth_mappings) > 0
                    chunks.append((rigid_vert_c, soft_vert_c, bone_map))
            
            lod_size = f.ReadInt32()
            if not lod_strip_flags.StripForServer(): vert_c = f.ReadInt32()
            required_bones = f.ReadArray(c_int16)
            if not lod_strip_flags.StripForEditor():
                bulk = BulkHeader().Read(f, asset.summary)
                if not (bulk.flags & (0x1 | 0x100)): # BULKDATA_PayloadAtEndOfFile | BULKDATA_PayloadInSeperateFile
                    if bulk.flags & 0x40: f.Seek(bulk.byte_size, mode=io.SEEK_CUR) # BULKDATA_ForceInlinePayload
            if asset.summary.version_ue4 >= 152: mesh_to_import_vert_map, max_import_vert_i = (f.ReadArray(c_int32), f.ReadInt32()) # VER_UE4_ADD_SKELMESH_MESHTOIMPORTVERTEXMAP
            
            vert_weights = []
            spl_norms = []

            if not lod_strip_flags.StripForServer(): # geometry TODO: var?
                uv_c = f.ReadInt32()

                ue_uvs = []
                mdl_uvs = []
                for i_uv in range(uv_c): mdl_uvs.append(bmsh.loops.layers.uv.new(f"UV{i_uv}"))

                if v_skel < 12: # SplitModelAndRenderData
                    # FSkeletalMeshVertexBuffer4 VertexBufferGPUSkin
                    vb_strip = ReadStripFlags(f, asset.summary, 269) # VER_UE4_STATIC_SKELETAL_MESH_SERIALIZATION_FIX
                    uv_c, float_uvs = (f.ReadInt32(), f.ReadBool32())
                    assert uv_c > 0 and uv_c < 32
                    if asset.summary.version_ue4 >= 334 and v_skel < 7: extra_bone_influences = f.ReadBool32() # VER_UE4_SUPPORT_GPUSKINNING_8_BONE_INFLUENCES & UseSeparateSkinWeightBuffer
                    else: extra_bone_influences = False
                    mesh_extension, mesh_origin = (f.ReadStructure(FVector), f.ReadStructure(FVector))
                    skel_infl_c = 8 if extra_bone_influences else 4
                    i_vert = 0

                    vert_type = FVector2D if float_uvs else FMeshUVHalf
                    el_size = f.ReadInt32() # ReadBulkArray
                    for i in range(f.ReadInt32()):
                        n_x, n_z = (f.ReadStructure(FPackedNormal).Unpack(), f.ReadStructure(FPackedNormal).Unpack())

                        if v_skel < 7: # UseSeparateSkinWeightBuffer, FSkinWeightInfo
                            assert skel_infl_c <= 4
                            bone_indices = f.ReadStructure(c_ubyte * skel_infl_c)
                            bone_weights = f.ReadStructure(c_ubyte * skel_infl_c)

                            vert_weights.append((bone_indices, bone_weights))
                            #for i_w in range(skel_infl_c): bone_groups[bone_indices[i_w]].add((i_vert,), bone_weights[i_w] / 255, 'REPLACE')
                        pos = f.ReadStructure(FVector)
                        uvs = f.ReadStructure(vert_type * uv_c)
                        ue_uvs.append(uvs)

                        vert = bmsh.verts.new(Vector((pos.y, pos.x, pos.z)))
                        vert.normal = n_z
                        i_vert += 1
                    
                    if v_skel >= 7: # UseSeparateSkinWeightBuffer
                        raise # FSkinWeightVertexBuffer SkinWeights
                    # TODO: LoadingMesh->bHasVertexColors? 
                    if not lod_strip_flags.StripClassData(1): adj_indices = ReadFMultisizeIndexContainer(f, asset.summary) # CDSF_AdjacencyData
                    if asset.summary.version_ue4 >= 254 and has_cloth_data: raise # VER_UE4_APEX_CLOTH
            
            bmsh.verts.ensure_lookup_table()
            for i in range(0, len(indices), 3):
                face = bmsh.faces.new((
                    bmsh.verts[indices[i+0]],
                    bmsh.verts[indices[i+1]],
                    bmsh.verts[indices[i+2]]
                ))

                n1 = bmsh.verts[indices[i+0]].normal
                n2 = bmsh.verts[indices[i+1]].normal
                n3 = bmsh.verts[indices[i+2]].normal
                spl_norms.append(Vector((n1.y, n1.x, n1.z)))
                spl_norms.append(Vector((n2.y, n2.x, n2.z)))
                spl_norms.append(Vector((n3.y, n3.x, n3.z)))

                loops = face.loops
                for i_uv in range(uv_c):
                    loops[0][mdl_uvs[i_uv]].uv = ue_uvs[indices[i+0]][i_uv].ToFloat2()
                    loops[1][mdl_uvs[i_uv]].uv = ue_uvs[indices[i+1]][i_uv].ToFloat2()
                    loops[2][mdl_uvs[i_uv]].uv = ue_uvs[indices[i+2]][i_uv].ToFloat2()
            
            bmsh.faces.ensure_lookup_table()
            for i_mat, i_base, tri_count in sections:
                i_tri_base = int(i_base/3)
                for i_tri in range(i_tri_base, i_tri_base + tri_count):
                    bmsh.faces[i_tri].material_index = i_mat

            bmsh.to_mesh(mesh)
            #mesh.normals_split_custom_set(spl_norms)
            if hasattr(mesh, 'use_auto_smooth'):
                mesh.use_auto_smooth = True
            mesh.transform(Matrix.Identity(4) * 0.01)

            for poly in mesh.polygons: poly.use_smooth = True

            i_vert = 0
            for rigid_vert_c, soft_vert_c, bone_map in chunks:
                for i in range(rigid_vert_c + soft_vert_c):
                    bone_indices, bone_weights = vert_weights[i_vert]
                    for i_w in range(skel_infl_c):
                        bone_groups[bone_map[bone_indices[i_w]]].add((i_vert,), bone_weights[i_w] / 255, 'REPLACE')
                    i_vert += 1

            if import_materials:
                for mat_imp in materials:
                    mesh.materials.append(TryGetUMaterialImport(mat_imp, mesh=mesh))

            return mesh
    else: raise # TODO
def ImportMeshUAsset(filepath:str, uproject=None, import_materials=True, log=False, o=None, all_lods=False):
    with UAsset(filepath, False, uproject) as asset:
        for export in asset.exports:
            match export.export_class_type:
                case 'StaticMesh': return ImportStaticMesh(export, import_materials, log, all_lods)
                case 'SkeletalMesh':
                    if all_lods: raise NotImplementedError('All source LODs currently supported for static meshes only')
                    return ImportSkeletalMesh(export, import_materials, o)
        if log: print(f"\"{filepath}\" Mesh Export Not Found")
    return None
def ImportUMeshAsObject(filepath:str, uproject=None, materials=True, all_lods=False):
    result = ImportMeshUAsset(filepath, uproject, materials, True, all_lods=all_lods)
    if result is None: raise ValueError('No mesh export found')
    meshes = result if isinstance(result,list) else [result]
    objects = []
    for i,mesh in enumerate(meshes):
        obj = next((o for o in bpy.data.objects if o.type=='MESH' and o.data==mesh),None)
        if obj is None:
            obj = bpy.data.objects.new(mesh.name,mesh)
            bpy.context.collection.objects.link(obj)
        if all_lods and i:
            obj.hide_set(True); obj.hide_render=True
        objects.append(obj)
    return objects

def menu_import_umesh(self, context): self.layout.operator(ImportUMesh.bl_idname, text="UE Mesh (.uasset)")
class ImportUMesh(bpy.types.Operator, ImportHelper):
    """Import Unreal Engine Mesh File"""
    bl_idname    = "import.umesh"
    bl_label     = "Import"
    filename_ext = ".uasset"
    filter_glob: StringProperty(default="*.uasset", options={'HIDDEN'}, maxlen=255)
    files:       CollectionProperty(type=bpy.types.OperatorFileListElement, options={'HIDDEN','SKIP_SAVE'})
    directory:   StringProperty(options={'HIDDEN'})

    materials:   BoolProperty(name="Materials", default=True, description="Import Mesh Materials (this is usually the slowest part).")

    all_lods: BoolProperty(name="All static source LODs", default=False, description="Import explicitly stored editor LOD meshes; lower-detail objects are hidden initially")

    def execute(self, context):
        paths = [os.path.join(self.directory,f.name) for f in self.files if f.name] or [self.filepath]
        successes, failures = 0, []
        for path in paths:
            try:
                ImportUMeshAsObject(path, materials=self.materials, all_lods=self.all_lods)
                successes += 1
            except Exception as exc:
                failures.append(f"{os.path.basename(path)}: {type(exc).__name__}: {exc}")
        for failure in failures: print(failure)
        self.report({'WARNING'} if failures else {'INFO'}, f"Imported {successes}/{len(paths)} mesh packages; {len(failures)} failed (see console)")
        return {'FINISHED'} if successes else {'CANCELLED'}

reg_classes = ( ImportUMesh, )

def register():
    addon_lifecycle.register(reg_classes, bpy.types.TOPBAR_MT_file_import, menu_import_umesh)
def unregister():
    addon_lifecycle.unregister(reg_classes, bpy.types.TOPBAR_MT_file_import, menu_import_umesh)

if __name__ != "umesh":
    importlib.reload(uasset)
    importlib.reload(umat)
    unregister()
    register()

    #filepath = r"F:\Projects\Unreal Projects\Assets\Content\ModSci_Engineer\Meshes\SM_Door_Small_A.uasset"
    #filepath = r"F:\Projects\Unreal Projects\Assets\Content\VehicleVarietyPack\Meshes\SM_Truck_Box.uasset"
    #filepath = r"F:\Projects\Unreal Projects\Assets\Content\VehicleVarietyPack\Meshes\SM_Hatchback.uasset"
    #filepath = r"F:\Projects\Unreal Projects\Assets\Content\VehicleVarietyPack\Meshes\SM_Pickup.uasset"
    #filepath = r"F:\Projects\Unreal Projects\Assets\Content\VehicleVarietyPack\Meshes\SM_SUV.uasset"
    #filepath = r"F:\Projects\Unreal Projects\Assets\Content\VehicleVarietyPack\Meshes\SM_SportsCar.uasset"
    #filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\ModSci_Engineer\Meshes\SM_Door_Small_A.uasset"
    #filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\VehicleVarietyPack\Meshes\SM_Truck_Box.uasset"
    #filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\ConstructionMachines\WheelLoader\SM_WheelLoader.uasset"
    #filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\FPS_Weapon_Bundle\Weapons\Meshes\Accessories\SM_Scope_25x56_X.uasset"
    filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\FPS_Weapon_Bundle\Weapons\Meshes\KA74U\SK_KA74U_X.uasset"
    #filepath = r"F:\Projects\Unreal Projects\Assets\Content\FPS_Weapon_Bundle\Weapons\Meshes\KA74U\SK_KA74U_X.uasset"
    #filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\FPS_Weapon_Bundle\Weapons\Meshes\SMG11\SK_SMG11_Nostock_Y.uasset"
    #filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\StarterBundle/ModularSci_Comm/Meshes/SM_Windows_A_Glass.uasset"
    #filepath = r"C:\Users\jdeacutis\Documents\Unreal Projects\Assets\Content\Military_VOL5_Devices\Meshes\SM_Generator_01d.uasset"
    #filepath = r"C:/Users/jdeacutis/Documents/Unreal Projects/Assets/Content/Military_VOL3_Checkpoint/Meshes/SM_Sandbags_02a.uasset"

    ImportUMeshAsObject(filepath)

    print("Done")