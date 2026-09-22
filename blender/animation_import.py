"""Animation conversion shared by regular imports and animation-only imports."""
import hashlib
import json
import math

import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

from ..xfbin_lib.xfbin.structure.anm import AnmDataPath, AnmEntryFormat
from .common.coordinate_converter import focal_to_blender


def bind_action(obj, action):
    obj.animation_data_create()
    obj.animation_data.action = action
    if hasattr(action, 'slots') and action.slots:
        action.slots[0].name_display = obj.name
        obj.animation_data.action_slot = action.slots[0]


def action_curves(action):
    if hasattr(action, 'fcurves'):
        return action.fcurves
    slot = action.slots[0] if action.slots else action.slots.new(id_type='OBJECT', name=action.name)
    layer = action.layers[0] if action.layers else action.layers.new('XFBIN')
    strip = layer.strips[0] if layer.strips else layer.strips.new(type='KEYFRAME')
    return strip.channelbag(slot, ensure=True).fcurves


def find_armature(clump, context, preferred=()):
    def matches(obj):
        if obj.type != 'ARMATURE':
            return False
        prop = getattr(obj, 'xfbin_clump_data', None)
        return (obj.get('源模型组') == clump.name or obj.get('xfbin_source_clump') == clump.name
                or (prop and prop.name == clump.name)
                or obj.name in (clump.name, clump.name + ' [C]'))
    candidates = [obj for obj in preferred if matches(obj)]
    if not candidates:
        candidates = [obj for obj in context.view_layer.objects if matches(obj)]
    if len(candidates) == 1:
        return candidates[0]
    active = context.view_layer.objects.active
    if active in candidates:
        return active
    if len(candidates) > 1:
        raise ValueError('Multiple armatures match %s; select the intended armature' % clump.name)
    return None


def new_action(name, anm, index, source):
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    action['xfbin_animation'] = anm.name
    action['xfbin_clump_index'] = index
    action['xfbin_source'] = source
    action['xfbin_loop'] = bool(anm.loop_flag)
    return action


def add_curve(action, path, index, frames, values, group, interpolation='LINEAR'):
    curves = action_curves(action)
    if curves.find(path, index=index):
        raise ValueError('Duplicate animation channel: ' + path)
    # Legacy fcurves accepts action_group; channel bags create groups separately.
    if hasattr(action, 'fcurves'):
        fc = curves.new(data_path=path, index=index, action_group=group)
    else:
        fc = curves.new(data_path=path, index=index)
    co = np.column_stack((frames, values)).astype(np.float32).ravel()
    if not np.isfinite(co).all():
        raise ValueError('Non-finite animation channel: ' + path)
    fc.keyframe_points.add(len(frames))
    fc.keyframe_points.foreach_set('co', co)
    enum = {i.identifier: i.value for i in fc.keyframe_points[0].bl_rna.properties['interpolation'].enum_items}
    fc.keyframe_points.foreach_set('interpolation', np.full(len(frames), enum[interpolation], dtype=np.int32))
    fc.update()


def sample_curve(curve, frames):
    keys = [k for k in curve.keyframes if k.frame >= 0]
    xs = np.array([k.frame * .01 for k in keys])
    values = np.array([k.value for k in keys], dtype=float)
    if values.ndim == 1:
        values = values[:, None]
    order = np.argsort(xs, kind='stable'); xs = xs[order]; values = values[order]
    keep = np.r_[xs[1:] != xs[:-1], True]; xs = xs[keep]; values = values[keep]
    if curve.interpolation == 'CONSTANT':
        return values[np.clip(np.searchsorted(xs, frames, side='right') - 1, 0, len(xs) - 1)]
    if curve.data_path == AnmDataPath.ROTATION_QUATERNION:
        quats = [Quaternion((v[3], *v[:3])).normalized() for v in values]
        result = []
        for frame in frames:
            j = int(np.searchsorted(xs, frame, side='right'))
            if not j: q = quats[0]
            elif j == len(xs): q = quats[-1]
            else: q = quats[j-1].slerp(quats[j], float((frame-xs[j-1])/(xs[j]-xs[j-1])))
            result.append((q.x, q.y, q.z, q.w))
        return np.array(result)
    return np.column_stack([np.interp(frames, xs, values[:, i]) for i in range(values.shape[1])])


def rest_matrix(bone):
    if 'orig_coords' not in bone:
        raise ValueError('Bone lacks original XFBIN rest coordinates: ' + bone.name)
    pos, rot, scale = bone['orig_coords']
    return Matrix.LocRotScale(Vector(pos)*.01, Euler(tuple(math.radians(v) for v in rot), 'ZYX'), Vector(scale))


def source_world(bone, cache):
    if bone.name not in cache:
        local = rest_matrix(bone)
        cache[bone.name] = source_world(bone.parent, cache) @ local if bone.parent else local
    return cache[bone.name]


def preserve_track(action, owner, curve, identity, label):
    keys = [k for k in curve.keyframes if k.frame >= 0]
    if not keys:
        return
    values = np.array([k.value for k in keys], dtype=float)
    if values.ndim == 1: values = values[:, None]
    if not np.isfinite(values).all():
        raise ValueError('Non-finite source track: ' + label)
    key = 'xfbin_track_' + hashlib.sha1(identity.encode('utf8')).hexdigest()[:20]
    owner[key] = values[0].tolist()
    owner.id_properties_ui(key).update(description=label + ' (source data; no shader/visibility driver)')
    path = ('' if isinstance(owner, bpy.types.ID) else owner.path_from_id()) + '["' + key + '"]'
    for i in range(values.shape[1]):
        add_curve(action, path, i, [k.frame*.01 for k in keys], values[:, i], 'Source tracks', curve.interpolation)


def convert_bone(action, rig, source_bone, world_cache):
    entry = source_bone.anm_entry
    if not entry:
        return False
    curves = [c for c in entry.curves if c and any(k.frame >= 0 for k in c.keyframes)]
    # The page-local reference resolves instance aliases to the actual coord name.
    target = getattr(source_bone, 'target_name', source_bone.name)
    bone = rig.data.bones.get(target)
    if bone is None:
        for i, curve in enumerate(curves):
            preserve_track(action, rig, curve, source_bone.name + '|' + str(i), 'Unmapped bone: ' + target)
        return False
    pb = rig.pose.bones[bone.name]
    pb.rotation_mode = 'QUATERNION'
    path = pb.path_from_id()
    transforms = [c for c in curves if c.data_path in (AnmDataPath.LOCATION, AnmDataPath.ROTATION_EULER,
                                                       AnmDataPath.ROTATION_QUATERNION, AnmDataPath.SCALE)]
    for i, curve in enumerate(curves):
        if curve not in transforms:
            preserve_track(action, pb, curve, source_bone.name + '|' + str(i), 'Opacity/material source channel')
    if not transforms:
        return False
    frames = np.unique([k.frame*.01 for c in transforms for k in c.keyframes if k.frame >= 0])
    # Bake every integer frame as well as exact source keys so mixed stepped and
    # interpolated channels retain their timing after rest-basis conversion.
    frames = np.unique(np.r_[frames, np.arange(math.ceil(frames[0]), math.floor(frames[-1])+1)])
    original = bone['orig_coords']
    adapter = source_world(bone, world_cache).inverted_safe() @ bone.matrix_local
    left = adapter.inverted_safe() @ rest_matrix(bone).inverted_safe()
    locations = np.tile(np.array(original[0])*.01, (len(frames), 1))
    rotations = [Euler(tuple(math.radians(v) for v in original[1]), 'ZYX').to_quaternion()] * len(frames)
    scales = np.tile(np.array(original[2]), (len(frames), 1))
    for curve in transforms:
        values = sample_curve(curve, frames)
        if not np.isfinite(values).all():
            raise ValueError('Non-finite source transform for bone ' + bone.name)
        if curve.data_path == AnmDataPath.LOCATION: locations = values*.01
        elif curve.data_path == AnmDataPath.ROTATION_EULER:
            rotations = [Euler(tuple(math.radians(v) for v in row), 'ZYX').to_quaternion() for row in values]
        elif curve.data_path == AnmDataPath.ROTATION_QUATERNION:
            rotations = [Quaternion((row[3], *row[:3])).normalized().conjugated() for row in values]
        elif curve.data_path == AnmDataPath.SCALE: scales = values
    rows = []; previous = None
    for i in range(len(frames)):
        matrix = left @ Matrix.LocRotScale(Vector(locations[i]), rotations[i], Vector(scales[i])) @ adapter
        loc, rot, scale = matrix.decompose()
        if not all(math.isfinite(v) for v in rot) or rot.magnitude < 1e-12:
            safe = Vector([v if abs(v)>1e-12 else 1.0 for v in scales[i]])
            _, rot, _ = (left @ Matrix.LocRotScale(Vector(locations[i]), rotations[i], safe) @ adapter).decompose()
        if previous is not None and rot.dot(previous) < 0: rot.negate()
        previous = rot.copy(); rows.append((*loc, *rot, *scale))
    rows = np.array(rows)
    for name, offset, width, source_paths in (
        ('location', 0, 3, (AnmDataPath.LOCATION,)),
        ('rotation_quaternion', 3, 4, (AnmDataPath.ROTATION_EULER, AnmDataPath.ROTATION_QUATERNION)),
        ('scale', 7, 3, (AnmDataPath.SCALE,))):
        interpolation = 'CONSTANT' if any(c.interpolation == 'CONSTANT' and c.data_path in source_paths for c in transforms) else 'LINEAR'
        for i in range(width): add_curve(action, path+'.'+name, i, frames, rows[:, offset+i], bone.name, interpolation)
    return True


def make_actions(anm, context, preferred=(), source=''):
    """Create retained Actions for every matching clump occurrence.

    A missing target is reported, not bound to an unrelated skeleton. Instances
    keep their own Action and index, even when Blender truncates their names.
    """
    actions = []; warnings = []
    for index, clump in enumerate(anm.clumps):
        rig = find_armature(clump, context, preferred)
        if rig is None:
            warnings.append('No matching armature: ' + clump.name)
            continue
        action = new_action(f'{anm.name} ({clump.name})', anm, index, source)
        try:
            action['xfbin_clump'] = clump.name
            action['xfbin_instance'] = getattr(clump, 'reference_name', clump.name)
            world_cache = {}; driven = 0
            for bone in clump.bones:
                driven += convert_bone(action, rig, bone, world_cache)
            if not len(action_curves(action)):
                bpy.data.actions.remove(action)
                continue
            action['xfbin_driven_bones'] = driven
            action['xfbin_data_only'] = not bool(driven)
            if not driven:
                warnings.append('Source tracks only, no matching animated bones: ' + clump.name)
            action['xfbin_external_parents'] = json.dumps([
                dict(child=p.child_coord_index, parent_clump=p.parent_clump_index, parent_bone=p.parent_coord_index)
                for p in anm.coord_parents if p.child_clump_index == index and p.parent_clump_index != index])
            for fc in action_curves(action): rig.path_resolve(fc.data_path)
            if hasattr(action, 'slots'):
                for slot in action.slots: slot.name_display = rig.name
            action['xfbin_target'] = rig.name
            actions.append(action)
            if not rig.animation_data or not rig.animation_data.action:
                bind_action(rig, action)
        except Exception:
            bpy.data.actions.remove(action)
            raise
    anm.import_warnings = warnings
    context.scene.render.fps = 30
    return actions


def make_camera_actions(anm, camera_chunks, context, collection, source=''):
    result = []
    for index, entry in enumerate(anm.other_entries):
        if entry.entry_format != AnmEntryFormat.CAMERA:
            anm.import_warnings.append('Unsupported non-skeletal entry: ' + entry.name)
            continue
        data = bpy.data.cameras.new(entry.name)
        data.lens_unit = 'MILLIMETERS'
        chunk = next((c for c in camera_chunks if c.name == entry.name and c.filePath == anm.filePath), None)
        if chunk is not None:
            data.lens = focal_to_blender(chunk.fov, data.sensor_width)
        obj = bpy.data.objects.new(entry.name + ' (' + anm.name + ')', data)
        collection.objects.link(obj)
        obj.rotation_mode = 'QUATERNION'
        action = new_action(anm.name + ' (camera)', anm, -1-index, source)
        try:
            for ci, curve in enumerate(entry.curves):
                if not curve:
                    continue
                keys = [k for k in curve.keyframes if k.frame >= 0]
                if not keys:
                    continue
                frames = [k.frame*.01 for k in keys]
                values = [k.value for k in keys]
                path = curve.data_path
                if path == AnmDataPath.LOCATION:
                    values = [[v*.01 for v in row] for row in values]
                    target = 'location'
                elif path == AnmDataPath.ROTATION_EULER:
                    values = [Euler(tuple(math.radians(v) for v in row), 'ZYX').to_quaternion()[:] for row in values]
                    target = 'rotation_quaternion'
                elif path == AnmDataPath.ROTATION_QUATERNION:
                    values = [Quaternion((row[3], *row[:3])).normalized().conjugated()[:] for row in values]
                    target = 'rotation_quaternion'
                elif path == AnmDataPath.CAMERA:
                    values = [(focal_to_blender(row[0], data.sensor_width),) for row in values]
                    target = 'data.lens'
                else:
                    preserve_track(action, obj, curve, str(ci), 'Camera source channel')
                    continue
                if target == 'rotation_quaternion':
                    for j in range(1, len(values)):
                        if sum(a*b for a,b in zip(values[j-1], values[j])) < 0:
                            values[j] = tuple(-v for v in values[j])
                for axis in range(len(values[0])):
                    add_curve(action, target, axis, frames, [v[axis] for v in values], entry.name, curve.interpolation)
            action['xfbin_target'] = obj.name
            bind_action(obj, action)
            result.append((obj, action))
        except Exception:
            bpy.data.actions.remove(action)
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.cameras.remove(data)
            raise
    return result
