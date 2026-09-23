"""Persistent action bundles controlled by one designated armature.

Only explicitly assembled objects participate. Pointer properties survive names
changing and save/reopen; no action-name or global skeleton matching is used.
"""
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, PointerProperty
from .animation_import import bind_action


class CombatBinding(bpy.types.PropertyGroup):
    target: PointerProperty(type=bpy.types.Object)
    action: PointerProperty(type=bpy.types.Action)
    apply_parent: BoolProperty(default=False)
    parent_target: PointerProperty(type=bpy.types.Object)


_busy = False
_last_actions = {}


def sync_scene(scene):
    global _busy
    if _busy or scene is None:
        return
    _busy = True
    try:
        for master in scene.objects:
            if not master.xfbin_combat_master:
                continue
            current = master.animation_data.action if master.animation_data else None
            key = (scene.as_pointer(), master.as_pointer())
            token = current.as_pointer() if current else 0
            if _last_actions.get(key) != token:
                _last_actions[key] = token
                if current and 'combat_frame_end' in current:
                    scene.frame_start = 0
                    scene.frame_end = max(1, int(current['combat_frame_end']))
            # An unrelated user action is not treated as a combat bundle.
            bindings = current.xfbin_combat_bindings if current else ()
            assigned = {b.target.as_pointer(): b.action for b in bindings if b.target and b.target != master}
            for binding in bindings:
                if binding.target and binding.apply_parent and binding.target.parent != binding.parent_target:
                    binding.target.parent = binding.parent_target
            if current and current.slots and master.animation_data.action_slot is None:
                master.animation_data.action_slot = current.slots[0]
            for member in master.xfbin_combat_members:
                target = member.target
                if not target or target == master:
                    continue
                action = assigned.get(target.as_pointer())
                enabled = int(action is not None)
                if target.get("xfbin_combat_enabled", 1) != enabled:
                    target["xfbin_combat_enabled"] = enabled
                old = target.animation_data.action if target.animation_data else None
                if action and (old != action or (action.slots and target.animation_data.action_slot is None)):
                    bind_action(target, action)
                elif not action and old:
                    target.animation_data.action = None
    finally:
        _busy = False


@persistent
def on_update(scene, *args):
    sync_scene(scene)


@persistent
def on_load(*args):
    _last_actions.clear()
    for scene in bpy.data.scenes:
        sync_scene(scene)


def configure_bundle(master, master_action, pairs):
    """pairs contains actual (object, action) references for this clip."""
    master.xfbin_combat_master = True
    master_action.use_fake_user = True
    master_action.xfbin_combat_bindings.clear()
    members = {m.target.as_pointer() for m in master.xfbin_combat_members if m.target}
    for target, action in pairs:
        if target == master:
            continue
        binding = master_action.xfbin_combat_bindings.add()
        binding.target = target
        binding.action = action
        if action:
            action.use_fake_user = True
        if target.as_pointer() not in members:
            member = master.xfbin_combat_members.add()
            member.target = target
            members.add(target.as_pointer())
        target["xfbin_combat_enabled"] = 1


def register():
    bpy.utils.register_class(CombatBinding)
    bpy.types.Action.xfbin_combat_bindings = CollectionProperty(type=CombatBinding)
    bpy.types.Object.xfbin_combat_members = CollectionProperty(type=CombatBinding)
    bpy.types.Object.xfbin_combat_master = BoolProperty(default=False)
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, on_update),
                               (bpy.app.handlers.frame_change_pre, on_update),
                               (bpy.app.handlers.load_post, on_load)):
        if callback not in handlers:
            handlers.append(callback)


def unregister():
    _last_actions.clear()
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, on_update),
                               (bpy.app.handlers.frame_change_pre, on_update),
                               (bpy.app.handlers.load_post, on_load)):
        if callback in handlers:
            handlers.remove(callback)
    del bpy.types.Object.xfbin_combat_master
    del bpy.types.Object.xfbin_combat_members
    del bpy.types.Action.xfbin_combat_bindings
    bpy.utils.unregister_class(CombatBinding)
