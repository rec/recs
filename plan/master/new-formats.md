# New data domains and interchange formats

Part of the [master proposal](master.md). These are candidate domains for
future editing and interchange work. They do not authorize implementation,
expand the current schema, or bring video into scope.

## Candidate data domains

- Still-image slideshows: image assets, display intervals, crops, transitions,
  captions, and cue points.
- Automation curves: parameter changes for instruments, lights, mixers, and
  effects.
- Cue sheets: markers, countdowns, operator notes, conditional actions, and
  rehearsal annotations.
- MIDI 2.0 and UMP streams: groups, per-note expression, SysEx7, SysEx8, and
  raw packet preservation.
- Device patches: lossless dumps, understood fields, bounded edits, and
  provenance.
- Lighting and pixel fields: fixture parameters, spatial LED frames, palettes,
  and physical patches.
- Control-voltage and gate lanes: volts, calibration profiles, trigger widths,
  and safety bounds.
- Analysis tracks: pitch, loudness, onset, tempo, spectral features, confidence,
  and availability latency.
- Broadcast rundowns: planned sections, live inputs, fallbacks, as-aired
  decisions, and rebroadcast edits.
- Interactive performance captures: keys, pedals, breath, gesture, sensors,
  and mapped semantic controls.

Further possibilities include stage automation, spatial audio, notation and
rehearsal material, robotics and kinetic sculpture, haptics, environmental
measurements, interactive-installation sensors, projection mapping metadata,
networked collaborative state, score following, digital fabrication, and
accessibility tracks. Projection mapping may describe surfaces, transforms,
masks, calibration points, and still-image placements; it does not add video
editing or video codecs to the proposal.

## Existing interchange formats

Almost every candidate domain has a digital format. The important distinction
is between a durable interchange standard and a vendor or project-specific
format whose bytes should initially remain opaque.

| Area | Existing formats | Planning implication |
| --- | --- | --- |
| Stage and lighting control | DMX512, Art-Net, sACN/E1.31, GDTF, MVR | Separate fixture/scene description from live transport and physical patching |
| Spatial audio | ADM/BWF, BW64 | Retain audio objects, channel layouts, and timed metadata separately from rendered channels |
| Notation and rehearsal | MusicXML, MEI, MIDI, SMuFL, LilyPond | Preserve notation meaning and engraving separately from performance playback |
| Robotics and kinetic work | ROS messages, rosbag, URDF, SDF, PLC and MQTT formats | Model safety limits and measured feedback before control delivery |
| Haptics | AHAP, Android haptic compositions, controller effects | Expect platform-specific adapters; no dominant interchange format exists |
| Environmental sensors | OGC SensorThings, SensorML, Observations and Measurements, NetCDF, CSV, MQTT | Preserve units, calibration, uncertainty, source time, and observation time |
| Interactive installations | OSC, MIDI, DMX, MQTT, WebSockets | Preserve raw traffic; project-specific event meaning needs an explicit adapter |
| Projection and spatial scenes | SVG, glTF, USD, MPCDI, vendor warp/blend formats | Keep geometry, still-image placement, and calibration distinct from endpoint delivery |
| Networked collaboration | Automerge, Yjs, operational transforms, JSON Patch | Treat ownership and conflict decisions as run or editing state, not implicit merges |
| Score following | MusicXML or MEI with MIDI/audio alignment data | No widely adopted interchange format represents live score position and confidence |
| Digital fabrication | G-code, STEP/STEP-NC, DXF, SVG, 3MF | Treat machine limits and material settings as binding-specific safety data |
| Accessibility | WebVTT, TTML/IMSC, EBU-TT, BRF | Caption interchange is mature; audio-description and sign-language cues are less standardized |

The strongest future candidates for structured import are ADM/BWF, MusicXML or
MEI, GDTF/MVR, glTF, SensorThings observations, and STEP/3MF. Each separates
meaning from at least some realization details. Formats with weak interchange
should enter first as sealed assets with a documented decoder or adapter,
rather than forcing their incomplete semantics into generic fields.

## References

- [Open Sound Control 1.0](https://opensoundcontrol.stanford.edu/spec-1_0.html)
- [GDTF and MVR overview](https://gdtf-share.com/help/)
- [ANSI E1.31 streaming ACN](https://tsp.esta.org/tsp/documents/docs/E1-31-2016.pdf)
- [Audio Definition Model usage guidance](https://www.itu.int/dms_pub/itu-r/opb/rep/R-REP-BS.2388-6-2025-TOC-HTM-E.htm)
- [glTF 2.0 specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html)
- [SMuFL](https://www.smufl.org/)

## Additional work beyond the prompt

None.
