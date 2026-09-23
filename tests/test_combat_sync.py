"""Run headlessly with Blender --python-exit-code 1 --python this_file."""
import bpy
import importlib
import tempfile
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
plugin = importlib.import_module(root.name)
plugin.register()
sync = importlib.import_module(root.name + ".blender.combat_sync")
conv = importlib.import_module(root.name + ".blender.animation_import")

def object(name):
    obj = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(obj)
    return obj

def action(name, value):
    a = bpy.data.actions.new(name)
    conv.add_curve(a, "location", 0, [0, 10], [value, value + 10], "Test")
    return a

master, weapon, susano = [object(n) for n in ("Master", "Weapon", "Susano")]
a, b, wa, wb, sa = [action(n, v) for n, v in (("A", 0), ("B", 20), ("WA", 1), ("WB", 21), ("SA", 4))]
sync.configure_bundle(master, a, [(weapon, wa), (susano, sa)])
sync.configure_bundle(master, b, [(weapon, wb)])
for bundle,parent in ((a,susano),(b,None)):
    binding=next(v for v in bundle.xfbin_combat_bindings if v.target==weapon)
    binding.apply_parent=True
    binding.parent_target=parent
a['combat_frame_end'] = 10
b['combat_frame_end'] = 42

# Use ordinary action assignment; do not call sync_scene explicitly.
master.animation_data_create()
master.animation_data.action = a
bpy.context.view_layer.update()
bpy.context.scene.frame_set(5)
assert weapon.animation_data.action == wa
assert weapon.parent == susano
assert bpy.context.scene.frame_end == 10
assert susano.animation_data.action == sa
assert abs(weapon.location.x - 6) < 1e-5
master.animation_data.action = b
bpy.context.view_layer.update()
bpy.context.scene.frame_set(6)
assert weapon.animation_data.action == wb
assert weapon.parent is None
assert bpy.context.scene.frame_end == 42
assert abs(weapon.location.x - 27) < 1e-5
assert susano.animation_data.action is None
assert susano["xfbin_combat_enabled"] == 0
master.animation_data.action = a
bpy.context.view_layer.update()
assert susano.animation_data.action == sa
assert susano["xfbin_combat_enabled"] == 1
master.name = "Renamed master"
wa.name = "Renamed weapon action"
with tempfile.TemporaryDirectory() as tmp:
    path = str(Path(tmp) / "sync.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    master = bpy.data.objects["Renamed master"]
    master.animation_data.action = bpy.data.actions["B"]
    bpy.context.scene.frame_set(7)
    weapon = bpy.data.objects["Weapon"]
    assert weapon.animation_data.action == bpy.data.actions["WB"]
    assert weapon.parent is None
    assert bpy.context.scene.frame_end == 42
    assert weapon.animation_data.action_slot is not None
    assert abs(weapon.location.x - 28) < 1e-5
    master.animation_data.action = None
    bpy.context.view_layer.update()
    assert weapon.animation_data.action is None
    assert weapon["xfbin_combat_enabled"] == 0
plugin.unregister()
print("COMBAT_SYNC_OK")
