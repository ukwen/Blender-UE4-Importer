"""Bounded editor Blueprint defaults via explicit CDO/SCS variable bindings.
References are recovered separately from placement; construction scripts are never run.
"""
from pathlib import Path
import uasset
from material_stage import package_reference


def checked_props(e):
    f=e.asset.f
    f.Seek(e.serial_desc.offset)
    p=uasset.Properties().Read(e.asset,read_children=False)
    if f.Position()>e.serial_desc.offset+e.serial_desc.count:
        raise ValueError('Blueprint property extent exceeded')
    return p


def value(p,key,default=None):
    return p.TryGetValue(key,default)


def read_bindings(asset,class_name,read=checked_props):
    classes=[(i,e) for i,e in enumerate(asset.exports,1) if e.outer_index==0 and e.export_class_type=='BlueprintGeneratedClass' and e.object_name==class_name]
    if len(classes)!=1: raise ValueError('Generated class not unique')
    ci,cls=classes[0]
    bindings={}
    def add(name,template,origin):
        if not isinstance(name,str) or not name or not isinstance(template,uasset.Export): raise ValueError('Invalid Blueprint component binding')
        if template.export_class_type not in ('StaticMeshComponent','SkeletalMeshComponent','InstancedStaticMeshComponent','HierarchicalInstancedStaticMeshComponent','SceneComponent','CapsuleComponent'): return
        p=read(template); field='SkeletalMesh' if template.export_class_type=='SkeletalMeshComponent' else 'StaticMesh'
        ref=value(p,field)
        if ref is not None and not package_reference(ref): raise ValueError('Invalid template mesh reference')
        from blueprint_placement import transform4
        item={'fields':transform4(p) if origin=='SCS' else {},'class':template.export_class_type,'package':package_reference(ref),'explicit':field in p,'origin':origin,'template':template.object_name}
        if name in bindings and bindings[name]!=item: raise ValueError('Ambiguous Blueprint component binding: '+name)
        bindings[name]=item
    # CDO component pointers are explicit property-name associations, not name guesses.
    cdos=[(i,e) for i,e in enumerate(asset.exports,1) if e.class_index==ci and e.object_name=='Default__'+class_name and e.outer_index==0]
    if len(cdos)>1: raise ValueError('Ambiguous class default object')
    if cdos:
        i,cdo=cdos[0]
        for name,prop in read(cdo).items():
            t=getattr(prop,'value',None)
            if isinstance(t,uasset.Export) and t.outer_index==i: add(name,t,'CDO')
    scripts=[(i,e) for i,e in enumerate(asset.exports,1) if e.outer_index==ci and e.export_class_type=='SimpleConstructionScript']
    if len(scripts)>1: raise ValueError('Ambiguous SimpleConstructionScript')
    for i,script in scripts:
        for entry in value(read(script),'AllNodes',[]):
            node=entry.value
            if not isinstance(node,uasset.Export) or node.outer_index!=i or node.export_class_type!='SCS_Node': raise ValueError('Invalid SCS node reference')
            p=read(node); t=value(p,'ComponentTemplate'); name=value(p,'InternalVariableName')
            if not isinstance(t,uasset.Export) or t.outer_index!=ci: raise ValueError('External SCS template unsupported')
            add(name,t,'SCS')
            if name in bindings:
                bindings[name]['socket']=value(p,'AttachToName','None')
                bindings[name]['parent']=value(p,'ParentComponentOrVariableName','None')
    return bindings


class BlueprintResolver:
    def __init__(self,project):
        self.project=project; self.cache={}; self.resolved_cache={}

    def load_local(self,key):
        package=key[0]
        if key not in self.cache:
            a=None
            try:
                if not package: raise ValueError('Missing Blueprint package reference')
                path=Path(self.project.resolve_package(package))
                if not path.is_file(): raise FileNotFoundError('Blueprint package unavailable')
                if path.with_suffix('.uexp').is_file(): raise NotImplementedError('Cooked Blueprint defaults unsupported')
                from package_inspector import inspect_package
                meta=inspect_package(path)
                if meta.get('ue5') is not None:
                    from ue5_blueprint import inspect_blueprint
                    result=inspect_blueprint(path)
                    if result['generated_class']!=key[1]: raise ValueError('Generated class mismatch')
                    bindings={}
                    for c in result['components']:
                        name=c['variable']
                        if not name or name in bindings: raise ValueError('Ambiguous Blueprint component binding')
                        bindings[name]={k:c[k] for k in ('package','explicit','origin','template','socket','parent','fields')}
                        bindings[name]['class']=c['kind']
                    self.cache[key]={'package':package,'class':key[1],'status':'inspected','bindings':bindings,'ue5':result['version'],'parent_blueprint':result['parent_blueprint'],'parent_class':result['parent_class'],'mesh_dependencies':result['mesh_dependencies']}
                    return self.cache[key]
                a=uasset.UAsset(str(path),False,self.project); a.Read(False)
                if not 516<=a.summary.version_ue4<=522: raise NotImplementedError('Unsupported Blueprint package version')
                bindings=read_bindings(a,key[1])
                from blueprint_placement import package4
                cls=next(e for e in a.exports if e.outer_index==0 and e.export_class_type=='BlueprintGeneratedClass' and e.object_name==key[1])
                parent=a.GetImport(cls.super_index) if cls.super_index<0 else None
                self.cache[key]={'package':package,'class':key[1],'status':'inspected','bindings':bindings,
                                 'parent_blueprint':package4(a,cls.super_index),'parent_class':parent.object_name if parent else ''}
            except Exception as exc:
                self.cache[key]={'package':package,'class':key[1],'status':'missing' if isinstance(exc,FileNotFoundError) else 'unresolved','detail':str(exc),'bindings':{}}
            finally:
                if a is not None and hasattr(a,'f'): a.Close()
        return self.cache[key]

    def load(self,actor):
        key=(package_reference(actor.export_class),actor.export_class_type)
        # Keep the local cache separate; ancestral merges must never overwrite
        # local declarations used by another child.
        if key in self.resolved_cache: return self.resolved_cache[key]
        local=self.load_local(key)
        if local.get('status')!='inspected': return local
        from blueprint_lineage import resolve_lineage
        result=dict(local)
        result.update(resolve_lineage(key,self.load_local))
        self.resolved_cache[key]=result
        return result

    def component(self,actor,component):
        result=self.load(actor); bindings=result['bindings']
        candidates=[bindings[name] for name,prop in actor.properties.items() if getattr(prop,'value',None) is component and name in bindings and bindings[name]['class']==component.export_class_type]
        if not candidates or any(c!=candidates[0] for c in candidates): return None
        return candidates[0]
