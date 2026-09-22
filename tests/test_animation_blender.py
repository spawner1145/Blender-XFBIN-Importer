"""blender -b --factory-startup --python-exit-code 1 --python tests/test_animation_blender.py"""
import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
plugin = importlib.import_module(ROOT.name)
plugin.register()
converter = importlib.import_module(ROOT.name + '.blender.animation_import')
anm = importlib.import_module(ROOT.name + '.xfbin_lib.xfbin.structure.anm')

bpy.ops.object.armature_add()
rig = bpy.context.object
rig.name = 'character [C]'
rig.data.bones[0].name = 'actual_bone'
rig.data.bones[0]['orig_coords'] = [[0., 0., 0.], [0., 0., 0.], [1., 1., 1.]]
curve = anm.create_anm_curve(anm.AnmDataPath.LOCATION, 0x1A, [(0,0,0), (100,0,0)], 100)
source_bone = NS(name='alias', target_name='actual_bone', anm_entry=NS(curves=[curve]))
clump = NS(name='character', reference_name='instance', bones=[source_bone], models=[])
clip = NS(name='very_long_animation_'*8, filePath='test', loop_flag=False, frame_count=100,
          frame_size=100, clumps=[clump, clump], coord_parents=[], other_entries=[])
original = bpy.data.actions.new('Existing animation')
converter.add_curve(original, 'location', 0, [0], [0], 'Object')
converter.bind_action(rig, original)
actions = converter.make_actions(clip, bpy.context)
assert len(actions) == 2 and actions[0] != actions[1]
assert rig.animation_data.action == original
assert all(a.use_fake_user for a in actions)
for action in actions:
    converter.bind_action(rig, action)
    assert rig.animation_data.action_slot is not None
    bpy.context.scene.frame_set(1)
    assert abs(rig.pose.bones['actual_bone'].location.x - 1) < 1e-5
    assert all(k.interpolation == 'CONSTANT' for fc in converter.action_curves(action)
               if fc.data_path.endswith('location') for k in fc.keyframe_points)

# Zero scale and raw material curves must remain finite and resolvable.
scale = anm.create_anm_curve(anm.AnmDataPath.SCALE, 0x1A, [(0,0,0)], 100)
material = anm.create_anm_curve(anm.AnmDataPath.UNKNOWN, 0x18, [(0.5,)], 100)
source_bone.anm_entry.curves = [scale, material]
zero_actions = converter.make_actions(clip, bpy.context)
assert len(zero_actions) == 2

empty = bpy.data.objects.new('#XFBIN Animations [test]', None)
bpy.context.collection.objects.link(empty)
item = empty.xfbin_anm_chunks_data.anm_chunks.add()
item.init_data(clip, actions, None)
rig.name = 'Renamed rig'
actions[0].name = 'Renamed action'
assert item.anm_clumps[0].target == rig
bpy.context.view_layer.objects.active = empty
item.clump_index = 1
assert bpy.ops.obj.play_animation() == {'FINISHED'}
assert rig.animation_data.action == actions[1]
item.clump_index = 0
assert bpy.ops.obj.play_animation() == {'FINISHED'}
assert rig.animation_data.action == actions[0]

# Camera-only chunks create a bound action, without relying on names.
cam_curve = anm.create_anm_curve(anm.AnmDataPath.CAMERA, 0x0C, [(0,60.),(100,45.)], 100)
clip.other_entries = [NS(name='camera', entry_format=anm.AnmEntryFormat.CAMERA, curves=[curve,cam_curve])]
cameras = converter.make_camera_actions(clip, [], bpy.context, bpy.context.collection)
assert len(cameras) == 1
camera, camera_action = cameras[0]
assert camera.animation_data.action_slot is not None
assert camera.path_resolve('data.lens') > 0
camera_only = empty.xfbin_anm_chunks_data.anm_chunks.add()
camera_only.name = 'Camera only'
camera_entry = camera_only.camera.add()
camera_entry.target = camera
camera_entry.action = camera_action
empty.xfbin_anm_chunks_data.anm_chunk_index = 1
assert bpy.ops.obj.play_animation() == {'FINISHED'}
assert bpy.context.scene.camera == camera
empty.xfbin_anm_chunks_data.anm_chunk_index = 0
with tempfile.TemporaryDirectory() as temp:
    path = str(Path(temp) / 'animation_test.blend')
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    empty = bpy.data.objects['#XFBIN Animations [test]']
    entry = empty.xfbin_anm_chunks_data.anm_chunks[0].anm_clumps[0]
    assert entry.target.name == 'Renamed rig' and entry.action.name == 'Renamed action'
    converter.bind_action(entry.target, entry.action)
    assert entry.target.animation_data.action_slot is not None
print('ANIMATION_REGRESSION_OK')
