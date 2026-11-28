"""Typed UE4.27 CDO and SCS association reader.

Uses the bounded package and property record contracts and original editor
fixtures. No Blueprint execution, inherited parser, or Blender dependency.
"""
import math
import struct
from package_records import read_editor522, ExportRecord, ImportRecord
from skeleton_native import Reader
from ue4_property_records import read_records

COMPONENTS = frozenset(('StaticMeshComponent', 'SkeletalMeshComponent',
    'InstancedStaticMeshComponent', 'HierarchicalInstancedStaticMeshComponent',
    'SceneComponent', 'CapsuleComponent'))
FIELDS = {'RelativeLocation': 'Vector', 'RelativeRotation': 'Rotator', 'RelativeScale3D': 'Vector'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


class BlueprintRecords:
    def __init__(self, path, class_name):
        _, self.raw, self.table = read_editor522(path)
        self.class_index, self.cls = self.unique(lambda e: not e.outer and e.kind == 'BlueprintGeneratedClass' and e.name == class_name)
        self.cdo = self.unique(lambda e: not e.outer and e.class_index == self.class_index and e.name == 'Default__'+class_name, optional=True)
        self.cache = {}

    def unique(self, predicate, optional=False):
        matches = [(i,e) for i,e in enumerate(self.table.exports,1) if predicate(e)]
        require(len(matches) == 1 or optional and not matches, 'Expected unique Blueprint export')
        return matches[0] if matches else None

    def props(self, entry):
        if entry not in self.cache:
            r = Reader(self.raw[entry.offset:entry.offset+entry.size])
            records = read_records(r, self.table.names)
            require(all(p.index == 0 for p in records), 'Indexed Blueprint properties unsupported')
            self.cache[entry] = {p.name:p for p in records}
        return self.cache[entry]

    def object_index(self, props, key):
        if key not in props:
            return 0
        p = props[key]
        require(p.kind == 'ObjectProperty' and len(p.data) == 4, 'Invalid object property: '+key)
        i = struct.unpack('<i',p.data)[0]
        self.table.reference(i)
        return i

    def name(self, props, key, default='None'):
        if key not in props:
            return default
        p = props[key]
        if p.kind == 'NameProperty' and len(p.data) == 8:
            return Reader(p.data).name(self.table.names)
        if p.kind == 'StrProperty':
            r = Reader(p.data); n = r.i()
            require(abs(n) <= 65536, 'String extent limit')
            b = r.take(n if n >= 0 else -2*n); term = bytes(1 if n >= 0 else 2)
            require(r.pos == len(p.data) and (not n or b.endswith(term)), 'Invalid string extent')
            return b[:-len(term)].decode('utf8' if n >= 0 else 'utf-16-le') if n else ''
        raise ValueError('Invalid name property: '+key)

    def fields(self, props):
        result = {}
        for key, kind in FIELDS.items():
            if key in props:
                p = props[key]
                require(p.kind == 'StructProperty' and p.parameters == (kind,) and len(p.data) == 12, 'Invalid transform: '+key)
                result[key] = struct.unpack('<3f',p.data)
                require(all(map(math.isfinite,result[key])), 'Nonfinite transform: '+key)
        for key in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale'):
            if key in props:
                require(props[key].kind == 'BoolProperty' and props[key].boolean is False, 'Absolute transform unsupported')
        return result

    def parent(self):
        i = self.cls.super_index
        ref = self.table.reference(i)
        return self.table.package(i,mounts=('/Game/','/Engine/','/Script/')), ref.name if isinstance(ref,ImportRecord) else ''

    def bindings(self):
        bindings = {}
        def add(name, entry, origin):
            require(isinstance(entry,ExportRecord) and name and name != 'None', 'Invalid component binding')
            if entry.kind not in COMPONENTS:
                return False
            p = self.props(entry); field = 'SkeletalMesh' if entry.kind == 'SkeletalMeshComponent' else 'StaticMesh'
            i = self.object_index(p,field)
            ref = self.table.reference(i)
            package = self.table.package(i) if isinstance(ref,ImportRecord) else ''
            require(not i or (package and ref.kind == field), 'Invalid template mesh reference')
            item = dict(fields=self.fields(p) if origin == 'SCS' else {}, **{'class':entry.kind}, package=package,explicit=field in p,origin=origin,template=entry.name)
            require(name not in bindings or bindings[name] == item, 'Ambiguous Blueprint component binding: '+name)
            bindings[name] = item
            return True
        if self.cdo:
            di,cdo = self.cdo; p = self.props(cdo)
            for name,record in p.items():
                if record.kind != 'ObjectProperty':
                    continue
                i = self.object_index(p,name); e = self.table.reference(i)
                if isinstance(e,ExportRecord) and e.outer == di:
                    add(name,e,'CDO')
        script = self.unique(lambda e:e.outer == self.class_index and e.kind == 'SimpleConstructionScript',optional=True)
        if script:
            si,e = script; p = self.props(e).get('AllNodes')
            if p is not None:
                require(p.kind == 'ArrayProperty' and p.parameters == ('ObjectProperty',), 'Invalid SCS nodes array')
                r = Reader(p.data); count = r.count(4096); indices = [r.i() for _ in range(count)]
                require(r.pos == len(p.data) and len(set(indices)) == count, 'Invalid SCS node array extent')
                for i in indices:
                    node = self.table.reference(i)
                    require(isinstance(node,ExportRecord) and node.outer == si and node.kind == 'SCS_Node','Invalid SCS node reference')
                    p = self.props(node); t = self.table.reference(self.object_index(p,'ComponentTemplate')); name = self.name(p,'InternalVariableName')
                    require(isinstance(t,ExportRecord) and t.outer == self.class_index,'External SCS template unsupported')
                    if add(name,t,'SCS'):
                        bindings[name].update(socket=self.name(p,'AttachToName'),parent=self.name(p,'ParentComponentOrVariableName'))
        return bindings

    def body_template(self):
        require(self.cdo is not None,'Missing class default object')
        di,cdo = self.cdo; p = self.props(cdo)
        mi,ri = self.object_index(p,'Mesh'),self.object_index(p,'RootComponent')
        m,root = self.table.reference(mi),self.table.reference(ri)
        require(isinstance(m,ExportRecord) and isinstance(root,ExportRecord) and self.object_index(p,'CapsuleComponent') == ri and m.outer == root.outer == di and m.kind == 'SkeletalMeshComponent' and root.kind == 'CapsuleComponent','Invalid CDO associations')
        mp,rp = self.props(m),self.props(root)
        require(self.object_index(mp,'AttachParent') == ri and not self.object_index(rp,'AttachParent') and self.name(mp,'AttachSocketName') == 'None','Unsupported CDO attachment')
        package,parent = self.parent(); require(self.cls.super_index < 0,'Unsupported parent class')
        return dict(mesh=m.name,root=root.name,parent_class=parent,parent_package=package,mesh_fields=self.fields(mp),root_fields=self.fields(rp))
