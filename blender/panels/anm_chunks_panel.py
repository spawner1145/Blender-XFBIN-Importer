from typing import List, Optional

import bpy
from bpy.props import (BoolProperty, CollectionProperty, IntProperty,
                       StringProperty, PointerProperty)
from bpy.types import Action, Panel, PropertyGroup

from ...xfbin_lib.xfbin.structure.nucc import NuccChunkAnm, NuccChunkCamera
from ...xfbin_lib.xfbin.structure.anm import AnmClump, AnmBone, AnmModel, AnmKeyframe
from ..common.helpers import XFBIN_ANMS_OBJ
from ..animation_import import make_actions, make_camera_actions, bind_action
from .common import draw_xfbin_list


class AnmClumpBonePropertyGroup(PropertyGroup):
    name: StringProperty()

    def init_data(self, bone: AnmBone):
        self.name = bone.name

class AnmClumpModelPropertyGroup(PropertyGroup):
    name: StringProperty()

    def init_data(self, model: AnmModel):
        self.name = model.name


class AnmClumpPropertyGroup(PropertyGroup):
    name: StringProperty(name="Name")
    clump_index: IntProperty(name="Index")
    action: PointerProperty(type=bpy.types.Action)
    target: PointerProperty(type=bpy.types.Object)
    models: CollectionProperty(type=AnmClumpModelPropertyGroup)
    model_index: IntProperty(name="Model Index")
    bones: CollectionProperty(type=AnmClumpBonePropertyGroup)
    bone_index: IntProperty(name="Bone Index")

    def init_data(self, clump: AnmClump):
        self.name = clump.name
        
        self.models.clear()
        for model in clump.models:
            item = self.models.add()
            item.init_data(model)
        
        self.bones.clear()
        for bone in clump.bones:
            item = self.bones.add()
            item.init_data(bone)
        

class CameraPropertyGroup(PropertyGroup):
    name: StringProperty()
    action: PointerProperty(type=bpy.types.Action)
    target: PointerProperty(type=bpy.types.Object)

    def init_data(self, camera: NuccChunkCamera):
        self.name = camera.name


class XfbinAnmChunkPropertyGroup(PropertyGroup):
    name: StringProperty(name="Name")

    path: StringProperty(name="Path")

    is_looped: BoolProperty(name="Looped", default=False)

    frame_count: IntProperty(name="Frame Count", default=0)

    frame_size: IntProperty(name="Frame Size", default=100)

    anm_clumps: CollectionProperty(
        type=AnmClumpPropertyGroup,
    )

    camera: CollectionProperty(
        type=CameraPropertyGroup,
    )

    clump_index: IntProperty(name="Clump Index")

    camera_index: IntProperty(name="Camera Index")
    
    def init_data(self, anm: NuccChunkAnm, actions: List[Action], camera: Optional[NuccChunkCamera]):
        self.name = anm.name
        self.path = anm.filePath
        self.is_looped = anm.loop_flag
        self.frame_count = anm.frame_count // anm.frame_size
        self.frame_size = anm.frame_size

        self.anm_clumps.clear()
        for index, clump in enumerate(anm.clumps):
            clump_prop: AnmClumpPropertyGroup = self.anm_clumps.add()
            clump_prop.init_data(clump)
            clump_prop.clump_index = index
            clump_prop.action = next((a for a in actions if a.get("xfbin_clump_index") == index), None)
            if clump_prop.action:
                clump_prop.target = bpy.data.objects.get(clump_prop.action["xfbin_target"])

        self.camera.clear()
        if camera is not None:
            camera_prop: CameraPropertyGroup = self.camera.add()
            camera_prop.init_data(camera)

        


class AnmChunksListPropertyGroup(PropertyGroup):
    anm_chunks: CollectionProperty(
        type=XfbinAnmChunkPropertyGroup,
    )

    anm_chunk_index: IntProperty()

    def init_data(self, anm_chunks, cam_chunks, context, preferred=(), source='', collection=None):
        self.anm_chunks.clear()
        for anm in anm_chunks:
            actions = make_actions(anm, context, preferred, source)
            item = self.anm_chunks.add()
            item.init_data(anm, actions, None)
            for obj, action in make_camera_actions(anm, cam_chunks, context, collection or context.collection, source):
                camera = item.camera.add()
                camera.name = obj.name
                camera.target = obj
                camera.action = action


class AnmChunksPropertyPanel(Panel):

    bl_idname = 'OBJECT_PT_xfbin_animation'
    bl_label = '[XFBIN] Animation Properties'

    bl_space_type = 'PROPERTIES'
    bl_context = 'object'
    bl_region_type = 'WINDOW'

    @classmethod
    def poll(cls, context):
        # get the outliner object
        
        obj = context.object
        return obj and obj.type == 'EMPTY' and obj.parent is None and obj.name.startswith(XFBIN_ANMS_OBJ)
    
    def draw(self, context):
        obj = context.object
        layout = self.layout
        data: AnmChunksListPropertyGroup = obj.xfbin_anm_chunks_data
        draw_xfbin_list(layout, 0, data, 'xfbin_anm_chunks_data', 'anm_chunks', 'anm_chunk_index')
        anm_index = data.anm_chunk_index

        box = layout.box()
        box.label(text="Animation Properties:")

        if anm_index >= 0 and anm_index < len(data.anm_chunks):
            chunk: XfbinAnmChunkPropertyGroup = data.anm_chunks[anm_index]
            box.prop(chunk, 'name')
            box.prop(chunk, 'path')
            box.prop(chunk, 'is_looped')
            
            row = box.row()
            row.prop(chunk, 'frame_count')
            row.prop(chunk, 'frame_size')

            #play button
            box.operator('obj.play_animation', text='Play Animation', icon='PLAY')      

            

            #clumps
            layout.label(text="Clumps:")
            anm = data.anm_chunks[anm_index]
            layout.label(text="Cameras:")
            draw_xfbin_list(layout, 4, anm, 'xfbin_anm_chunks_data.anm_chunks[anm_chunk_index]', 'camera', 'camera_index')
            if not 0 <= anm.clump_index < len(anm.anm_clumps):
                layout.label(text="No skeletal clumps")
                return
            clump = anm.anm_clumps[anm.clump_index]
            draw_xfbin_list(layout, 1, anm, 'xfbin_anm_chunks_data.anm_chunks[anm_chunk_index]', 'anm_clumps', 'clump_index')

            #models
            layout.label(text="Models:")
            draw_xfbin_list(layout, 2, clump, 'xfbin_anm_chunks_data.anm_chunks[anm_chunk_index].anm_clumps[clump_index]', 'models', 'model_index')

            #bones
            layout.label(text="Bones & Materials:")
            draw_xfbin_list(layout, 3, clump, 'xfbin_anm_chunks_data.anm_chunks[anm_chunk_index].anm_clumps[clump_index]', 'bones', 'bone_index')

class PlayAnimation(bpy.types.Operator):
    bl_idname = 'obj.play_animation'
    bl_label = 'Play Animation'
    bl_description = 'Play Animation'

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj and obj.type == 'EMPTY' and obj.parent is None and obj.name.startswith(XFBIN_ANMS_OBJ)
    
    def execute(self, context):
        data = context.object.xfbin_anm_chunks_data
        if not 0 <= data.anm_chunk_index < len(data.anm_chunks):
            return {'CANCELLED'}
        chunk = data.anm_chunks[data.anm_chunk_index]
        entries = list(chunk.anm_clumps)
        # The selected occurrence wins when multiple instances share one rig.
        if 0 <= chunk.clump_index < len(entries):
            entries.insert(0, entries.pop(chunk.clump_index))
        seen = set()
        duplicates = False
        for entry in entries + list(chunk.camera):
            if not entry.target or not entry.action:
                continue
            if entry.target.name in seen:
                duplicates = True
                continue
            bind_action(entry.target, entry.action)
            seen.add(entry.target.name)
            if entry.target.type == 'CAMERA':
                context.scene.camera = entry.target
        if not seen:
            self.report({'WARNING'}, 'No matching imported actions; import the target model first')
            return {'CANCELLED'}
        context.scene.frame_start = 0
        context.scene.frame_end = max(1, chunk.frame_count)
        context.scene.frame_set(0)
        if context.screen and not bpy.app.background and not context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()
        if duplicates:
            self.report({'WARNING'}, 'Shared rig: playing the selected clump occurrence; select another clump to switch')
        else:
            self.report({'INFO'}, 'Playing animation ' + chunk.name)
        return {'FINISHED'}


anm_chunks_property_groups = (
    AnmClumpBonePropertyGroup,
    AnmClumpModelPropertyGroup,
    AnmClumpPropertyGroup,
    CameraPropertyGroup,
    XfbinAnmChunkPropertyGroup,
    AnmChunksListPropertyGroup,
)

anm_chunks_classes = (
    *anm_chunks_property_groups,
    AnmChunksPropertyPanel,
    PlayAnimation
)
