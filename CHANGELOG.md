# 1.6.0 — Animation import fixes

- Decode stepped float3 (0x1A), int16 quaternion (0x1B), and opacity (0x1D)
  channels; reject unknown formats before they can desynchronize the reader.
- Resolve sparse channels by header index and bone instance aliases through
  page-local chunk references. Preserve separate animation occurrences per page.
- Convert source transforms against the imported bone rest basis, handle zero
  scales, retain signed transforms, and preserve non-transform source tracks.
- Add animation-only imports for existing XFBIN armatures, including direct
  operator invocation with filepath and file-browser multi-selection.
- Retain Actions with fake users, explicitly bind Blender action slots, and store
  persistent Action/Object pointers for playback after renaming and reopening.
- Preserve repeated clump instances as distinct Actions. The selected occurrence
  wins when instances share one armature; playback reports that choice.
- Keep camera animation support, including camera-only clips. Report missing
  targets and unsupported light tracks instead of silently discarding errors.
- Include parser unit tests and a portable headless Blender regression test.

The working tree also contains the earlier rigid bone-parent transform and
reflected-mesh winding corrections. These have been preserved in this release.
See README for import workflow and remaining runtime/retargeting limitations.
