# cc2_xfbin_blender
 Blender import/export script for CyberConnect2 games XFBIN files. The add-on metadata requires Blender 4.0 or later; animation fixes in version 1.6.0 were tested on Blender 5.2.
 
 Uses [xfbin_lib](https://github.com/SutandoTsukai181/xfbin_lib) for reading/writing XFBIN files.

# Installing
Download the [latest release](https://github.com/SutandoTsukai181/cc2_xfbin_blender/releases/latest) and install it in Blender. To do so, follow the instructions in the [official Blender manual](https://docs.blender.org/manual/en/latest/editors/preferences/addons.html) for installing add-ons, or follow the brief instructions below.

Open the `Edit` -> `Preferences` window from the menu bar, go to `Add-ons`, click on the `Install` button, and select the release zip you downloaded. Then, enable the script by checking the box next to it.

# Usage
Check the [wiki](https://github.com/SutandoTsukai181/cc2_xfbin_blender/wiki) for guides and usage info.

# Credits
Huge thanks to [TheTurboTurnip](https://github.com/theturboturnip) for his help with Blender related stuff, and for making the [Yakuza model importer/exporter](https://github.com/theturboturnip/yk_gmd_io) script, which was used as a reference for this project.

Thanks to the [Smash Forge](https://github.com/jam1garner/Smash-Forge) team for their NUD models and NUT textures implementation, which the NuccChunkModel and NuccChunkTexture classes use, respectively.

## Animation import (1.6.0)

Import the model first, then choose **File > Import > XFBIN** and enable
**Animations Only** to append animations from one or more XFBIN files to existing
XFBIN armatures. Normal model imports also use the corrected animation converter.
Select the `#XFBIN Animations` empty and use its **Animation Properties** panel to choose
and play a clip. For repeated clump instances sharing one armature, select the
wanted clump occurrence before playing. Each occurrence keeps a separate Action.
If multiple armatures match, make the intended armature active before importing.

Actions are retained when saving and use persistent object/action references in
the panel, including after renaming. Blender 4.4+ action slots are bound explicitly.
Missing target armatures are reported; import them and retry the animation file.
Bones must retain the original XFBIN `orig_coords` metadata. This is not a general
retargeter for arbitrary skeletons or costumes.

Opacity/material channels and unmapped bone channels are stored as custom-property
curves, not connected to shaders or visibility. Light animation entries are reported
as unsupported. External character/prop parenting dependencies are recorded on the
Action and are not automatically constrained. Streaming animation chunks are not
supported by the animation-only reader. Invalid/non-finite source data raises an
error; earlier successfully imported clips may remain and can be removed manually.
Transforms are baked at integer frames and exact source key times; subframe
interpolation after basis conversion is an approximation. No animation-export
round-trip guarantee is added by this release.

### 中文说明

先导入模型，再次导入 XFBIN 时勾选 **Animations Only（仅导入动画）**，
即可向已有 XFBIN 骨架追加文件中的匹配动作，支持多选文件。
在动画管理空物体的属性面板选择动作并播放。多个实例共用同一骨架时，
选择对应 Clump 后播放；各实例动作都保留，不再依赖动作名称查找。
骨架匹配有歧义时，请先激活目标骨架。缺少模型或不支持的轨道会报告警告。
材质、透明度和未匹配骨骼轨道仅保留数据，不代表游戏着色器、粒子特效
或跨角色约束已还原。更新正在运行的 Blender 后请重启，以加载新代码。

### Regression checks

```sh
python -m unittest discover -s tests -p test_animation_parser.py
blender -b --factory-startup --python-exit-code 1 --python tests/test_animation_blender.py
```

The tests include extended binary formats, sparse channel indices, reference aliases,
repeated/long action names, existing-action preservation, zero scales, camera slots,
and save/reopen reference persistence. Proprietary game assets are not bundled.
