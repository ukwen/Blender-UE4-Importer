"""Bounded editor Blueprint defaults via explicit CDO/SCS variable bindings.
References are recovered separately from placement; construction scripts are never run.
"""
from pathlib import Path
def package_reference(ref):
    from reference_identity import package_reference as resolve
    return resolve(ref)


class BlueprintResolver:
    def __init__(self,project):
        self.project=project; self.cache={}; self.resolved_cache={}

    def load_local(self,key):
        package=key[0]
        if key not in self.cache:
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
                if meta.get('ue4') == 522:
                    from classic_blueprint import BlueprintRecords
                    reader = BlueprintRecords(path,key[1]); parent_package,parent_class = reader.parent()
                    self.cache[key] = dict(package=package, **{'class':key[1]}, status='inspected', bindings=reader.bindings(), parent_blueprint=parent_package,parent_class=parent_class)
                    return self.cache[key]
                raise NotImplementedError('Unsupported native Blueprint defaults profile')
            except Exception as exc:
                self.cache[key]={'package':package,'class':key[1],'status':'missing' if isinstance(exc,FileNotFoundError) else 'unresolved','detail':str(exc),'bindings':{}}
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
