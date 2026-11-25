"""Synthetic raw source and PNG checks; genuine editor packages tested in Blender."""
import unittest
from editor_texture import source_png, validate_png
from native_texture import png_bytes

class SourceTests(unittest.TestCase):
    def test_raw_bgra_mips(self):
        raw=bytes([30,20,10,255])*4+bytes([60,50,40,255])
        self.assertEqual(source_png(raw,2,2,'TSF_BGRA8',2,False),png_bytes(2,2,bytes([10,20,30,255])*4))
    def test_raw_grayscale(self):
        self.assertEqual(source_png(bytes([7,120]),2,1,'TSF_G8',1,False),png_bytes(2,1,bytes([7,7,7,255,120,120,120,255])))
    def test_png_validation(self):
        png=png_bytes(1,1,bytes([10,20,30,255])); self.assertEqual(validate_png(png,1,1),png)
        for bad in (png[:-1],png+b'junk',png[:40]+bytes([png[40]^1])+png[41:]):
            with self.assertRaises(ValueError): validate_png(bad,1,1)
        with self.assertRaises(NotImplementedError): validate_png(png,2,1)
    def test_invalid_source(self):
        for raw in (b'',b'12345'):
            with self.assertRaises(ValueError): source_png(raw,1,1,'TSF_BGRA8',1,False)
        with self.assertRaises(NotImplementedError): source_png(b'',1,1,'TSF_RGBA16',1,False)
