# SubsLab 0.2.0

The app is now SubsLab. The Python module, legacy settings/application-data identities, Windows installer AppId, and macOS bundle ID remain unchanged so existing models and recovery snapshots remain accessible. `subslab` is the main launch command; `subsgen-studio` remains an alias.

## Workspace changes

- Shared charcoal/teal theme, standard desktop menus, compact header, and persistent workspace layout.
- Collapsible generation/advanced settings, prominent media filename, and a shared waveform/transport below the preview and editor.
- Yellow selected-cue border, separate teal current/playing state, contextual cue tools, and right-to-left subtitle editing with left-to-right timestamps.
- Model/backend/device/stage/elapsed-time progress, an always-accessible cancel button while processing, and explicit explanations for unfixable readability issues.

## Reliability and responsiveness

- Cue cards are reused by ID; structural edits and undo preserve unaffected editor widgets, cursor selection, and scroll position.
- Live edits validate the changed cue immediately and debounce the complete warning summary by 150 ms.
- The waveform background is cached between playhead updates, and unchanged caption overlays avoid redundant layout work.
- Keyboard undo/redo uses the same document history from text editors, menus, and toolbar actions.
- Model progress remains bound to the active operation and supports counters larger than 32-bit integers.
- Delayed cancellation cannot terminate a subsequent job; waveform threads shut down cooperatively.
- Save stops pending recovery writes; all subtitle export formats run final structural validation.
- Timeline edits preserve neighbor minimum durations and do not partially mutate the timeline on failure.
- Windows packaging excludes foreign `icuuc.dll` copies from the build host's PATH, allowing Qt to load Windows' native ICU API.

## Validation

The automated suite covers core subtitle handling, randomized timing repair/edit scenarios, RTL, card reuse, undo/redo, progress, cancellation, workspace persistence, and export. UI previews are rendered in normal and 200% display scaling, including the 1024×720 workspace.

Local verification on 15 October 2026: **99 tests passed**. The rebuilt Windows executable passed both offscreen and native Windows startup checks. The source ZIP includes the complete macOS build workflow; the refreshed Mac artifact has not yet been built or tested on real hardware.

Windows and macOS packaging use `SubsLab.spec`. The GitHub macOS workflow checks ARM64 architecture, DMG integrity, resources, and packaged application startup. These checks do not replace real-media playback testing on an Apple Silicon Mac. Real-model accuracy, CUDA, and Apple GPU checks require their respective models/hardware.

## Recommended next improvements

1. Timeline zoom and horizontal navigation for precise edits in long recordings.
2. Merge neighboring cues and edit multiple selected cues together.
3. Preview reflow/bulk-fix changes before applying them.
4. Drag-and-drop import and recent files.
5. Optional larger transcription models with clear speed, memory, and accuracy tradeoffs.
