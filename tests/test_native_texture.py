"""Regression tests for the bounded cooked texture reader; set MATYA_ASSETS for real samples."""
import io, os, shutil, struct, tempfile, unittest
from pathlib import Path
from native_texture import read_texture, decode_rgba, png_bytes


@unittest.skipUnless(os.environ.get('MATYA_ASSETS'), 'Set MATYA_ASSETS to extracted sample archive')
class RealTextureTests(unittest.TestCase):
    root = Path(os.environ.get('MATYA_ASSETS',''))

    def test_nine_genuine_packages(self):
        from PIL import Image
        for version in ('4.18','4.27','5.0'):
            for suffix,expected in [('A','PF_BC4'),('D','PF_DXT1'),('N','PF_BC5')]:
                with self.subTest(version=version,suffix=suffix):
                    path=self.root/version/f'T_Worm_{suffix}.uasset'
                    w,h,fmt,raw,count=read_texture(path,version)
                    self.assertEqual((w,h,fmt,count),(256,256,expected,1 if suffix=='N' else 9))
                    fourcc={'PF_DXT1':b'DXT1','PF_BC4':b'ATI1','PF_BC5':b'ATI2'}[fmt]
                    dds=b'DDS '+struct.pack('<7I',124,0x81007,h,w,len(raw),0,1)+bytes(44)+struct.pack('<II4s5I',32,4,fourcc,0,0,0,0,0)+struct.pack('<5I',0x1000,0,0,0,0)+raw
                    reference=Image.open(io.BytesIO(dds)).convert('RGBA')
                    actual=Image.open(io.BytesIO(png_bytes(w,h,decode_rgba(w,h,fmt,raw))))
                    channels=2 if suffix=='N' else 1 if suffix=='A' else 4
                    for i in range(channels):
                        self.assertEqual(reference.getchannel(i).tobytes(),actual.getchannel(i).tobytes())

    def test_reject_wrong_profile(self):
        with self.assertRaises(ValueError): read_texture(self.root/'4.27/T_Worm_D.uasset','5.0')

    def test_reject_truncated_or_missing_bulk(self):
        with tempfile.TemporaryDirectory() as temp:
            src=self.root/'4.27/T_Worm_D.uasset'; dst=Path(temp)/src.name
            for suffix in ('.uasset','.uexp','.ubulk'): shutil.copy(src.with_suffix(suffix),dst.with_suffix(suffix))
            bulk=dst.with_suffix('.ubulk'); bulk.write_bytes(bulk.read_bytes()[:-1])
            with self.assertRaises(ValueError): read_texture(dst,'4.27')
            bulk.unlink()
            with self.assertRaises(ValueError): read_texture(dst,'4.27')

    def test_reject_invalid_inline_offset(self):
        with tempfile.TemporaryDirectory() as temp:
            src=self.root/'4.27/T_Worm_N.uasset'; dst=Path(temp)/src.name
            shutil.copy(src,dst)
            data=bytearray(src.with_suffix('.uexp').read_bytes()); p=data.index(b'PF_BC5\0')+7+8+4+12
            struct.pack_into('<q',data,p,0); dst.with_suffix('.uexp').write_bytes(data)
            with self.assertRaises(ValueError): read_texture(dst,'4.27')
