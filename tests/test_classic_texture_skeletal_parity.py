"""Original Western corpus parity against the saved 0.10.102 decode baseline."""
import hashlib
import json
import os
import unittest
from pathlib import Path
from editor_texture import read_editor_texture
from legacy_skeletal import read_legacy_skeletal
from package_records import read_package


@unittest.skipUnless(os.environ.get('UE_WESTERN_PROJECT'),'Original Western fixture required')
class ClassicPayloadParity(unittest.TestCase):
    def test_original_payloads(self):
        result={'textures':{},'skeletal':{}}
        for p in sorted(Path(os.environ['UE_WESTERN_PROJECT']).rglob('*.uasset')):
            _,_,table=read_package(p)
            kinds={e.kind for e in table.exports if not e.outer}
            if 'Texture2D' in kinds:
                png,meta=read_editor_texture(p)
                result['textures'][p.name]={'sha':hashlib.sha256(png).hexdigest(),'meta':meta}
            if 'SkeletalMesh' in kinds:
                data=read_legacy_skeletal(p)
                result['skeletal'][p.name]=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual((len(result['textures']),len(result['skeletal'])),(14,31))
        self.assertEqual(hashlib.sha256(json.dumps(result,indent=2,sort_keys=True).encode()).hexdigest(),'9caa50ef83aac0ada52ef70eacb71c360b383a410b1fc973a4248fbda3a90fe4')
