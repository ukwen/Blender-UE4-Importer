"""Bounded RGB and explicit instance base-property semantics, independent of bpy."""
import math
import struct


def base_property_audit(history, base):
    """Only an explicit true flag authorizes an override; missing value blocks inheritance.

    Serialized values without an active flag are not active overrides. Only a
    finite explicit opacity threshold is translated; other active flags remain
    unresolved rather than guessing engine class defaults.
    """
    selected=set(); rows=[]; issues=[]
    for record in history:
        props=record['properties']
        for name in sorted({k.removeprefix('bOverride_') for k in props}):
            flag=props.get('bOverride_'+name); value=props.get(name)
            row=dict(property=name,source_package=record['source_package'],serialized_value=value,serialized_flag=flag)
            if flag is None:
                row['status']='inactive_no_flag'
            elif flag.get('type')!=['BoolProperty'] or flag.get('data')!='' or flag.get('flags',0)&0x28:
                row['status']='invalid_flag';selected.add(name);issues.append('Invalid base property flag: '+name)
            elif not flag['flags']&16:
                row['status']='inactive_false_flag'
            elif name in selected:
                row['status']='shadowed_by_child'
            else:
                selected.add(name);row['status']='active_unresolved'
                if name=='OpacityMaskClipValue' and value and value.get('type')==['FloatProperty'] and not value.get('flags',0)&0x28:
                    try:
                        clip=struct.unpack('<f',bytes.fromhex(value['data']))[0]
                        if math.isfinite(clip) and 0.<clip<=1.:
                            base['opacity_mask_clip']=clip;row.update(status='applied',value=clip)
                    except (ValueError,struct.error,KeyError):pass
                if row['status']!='applied':
                    row['detail']='Active flag but serialized value absent' if value is None else 'Active property translation unsupported or invalid'
                    issues.append('Unresolved base property: '+name)
            rows.append(row)
    return rows,issues


def rgb_lerp(a,b,f,*,components,combine,mathop,label):
    """Scalar or RGB channels only; no float4/alpha claim."""
    if any(s.type not in ('VALUE','RGBA','VECTOR') for s in (a,b,f)):
        raise ValueError('Unsupported interpolation operands')
    def lerp(x,y,t):return mathop('ADD',x,mathop('MULTIPLY',mathop('SUBTRACT',y,x),t),label)
    if a.type==b.type==f.type=='VALUE':return lerp(a,b,f)
    result=combine([lerp(x,y,t) for x,y,t in zip(components(a),components(b),components(f))],label+' (unclamped RGB)')
    result.node['UE_unclamped_lerp']=True
    if f.type!='VALUE':result.node['UE_rgb_factor_preview']=True
    return result
