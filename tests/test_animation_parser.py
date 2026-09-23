"""Run with Python: python -m unittest discover -s tests -p test_animation_parser.py"""
import importlib
from pathlib import Path
import struct
import sys
from types import SimpleNamespace as NS
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
base = ROOT.name + '.xfbin_lib.xfbin'
anm = importlib.import_module(base + '.structure.anm')
br_anm = importlib.import_module(base + '.structure.br.br_anm')
util = importlib.import_module(base + '.util')

class AnimationParserTests(unittest.TestCase):
    def read_entry(self, fmt, payload, index=0):
        header = struct.pack('>hHHHHHHh', 0, 0, 1, 1, index, fmt, 1, 0)
        payload += b'\0' * (-len(payload) % 4)
        return util.BinaryReader(header + payload, util.Endian.BIG).read_struct(br_anm.BrAnmEntry)

    def test_extended_formats(self):
        for fmt, binary_fmt, values, path in [
            (0x1A, '>3f', (1, 2, 3), anm.AnmDataPath.LOCATION),
            (0x1B, '>4h', (0, 0, 0, 32767), anm.AnmDataPath.ROTATION),
            (0x1D, '>h', (16384,), anm.AnmDataPath.TOGGLED),
        ]:
            entry = self.read_entry(fmt, struct.pack(binary_fmt, *values))
            curve = anm.create_anm_curve(path, fmt, entry.curves[0], 100)
            self.assertEqual(curve.interpolation, 'CONSTANT')
            self.assertEqual(len(curve.keyframes), 1)
        self.assertEqual(curve.keyframes[0].value, (0.5,))

    def test_opacity_is_unsigned(self):
        for fmt in (0x0F, 0x1D):
            raw = self.read_entry(fmt, struct.pack('>H', 65535))
            curve = anm.create_anm_curve(anm.AnmDataPath.TOGGLED, fmt, raw.curves[0], 100)
            self.assertEqual(curve.keyframes[0].value, (65535 / 32768,))

    def test_unknown_format_fails(self):
        with self.assertRaisesRegex(ValueError, 'unsupported curve format'):
            self.read_entry(0xFE, b'')

    def test_sparse_rotation_keeps_index(self):
        raw = self.read_entry(0x1B, struct.pack('>4h', 0, 0, 0, 32767), index=1)
        bone = anm.AnmBone()
        entry = anm.AnmEntry()
        entry.init_data(raw, 100, [NS(bones=[bone])], [])
        self.assertIsNone(entry.location_curve)
        self.assertEqual(entry.rotation_curve.data_path, anm.AnmDataPath.ROTATION_QUATERNION)

    def test_keyed_opacity_timing(self):
        curve = anm.create_anm_curve(anm.AnmDataPath.TOGGLED, 0x0C, [(350, .25)], 100)
        self.assertEqual(curve.keyframes[0].frame, 350)
        self.assertEqual(curve.keyframes[0].value, (.25,))

    def test_reference_alias_resolves_coord(self):
        clump = anm.AnmClump()
        clump.init_data(NS(clump_index=0, bones=[1], models=[]), [
            NS(name='instance_2', chunk=NS(name='character')),
            NS(name='instance_2_arm', chunk=NS(name='actual_arm'))])
        self.assertEqual(clump.reference_name, 'instance_2')
        self.assertEqual(clump.bones[0].target_name, 'actual_arm')

    def test_unsigned_parent_sentinel(self):
        nucc = importlib.import_module(base + '.structure.nucc')
        raw = NS(data=b'', frame_count=100, frame_size=100, loop_flag=0,
                 clumps=[], entries=[], other_entry_indices=[],
                 coord_parents=[NS(parent_clump_index=0, child_clump_index=0,
                                   parent_coord_index=65535, child_coord_index=0)])
        chunk = nucc.NuccChunk.create_from_nucc_type('nuccChunkAnm', 'test', 'test')
        chunk.init_data(raw, [], [], [])
        raw.coord_parents[0].parent_coord_index = 0
        with self.assertRaisesRegex(ValueError, 'clump index'):
            chunk.init_data(raw, [], [], [])

if __name__ == '__main__':
    unittest.main()
