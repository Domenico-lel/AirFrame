# AirFrame interface

The user's photo is the visual authority: a floating phone with a slim detached dark toolbar. Mode: Operate. No sidebar or dashboard.

## Tokens

- Typeface: Segoe UI on Windows, 12 px controls, 10 px secondary toolbar text, 14 px empty-state text.
- Toolbar: #292d36, 48 px tall, radius 10 px.
- Screen waiting surface: #101319; primary text #f2f3f5.
- Secondary text: #c0c8d4; status text #d2d8e2 on #252a33.
- Frame: #17191e body, #737982 outer edge, #30343c inner edge.
- Buttons: 30 × 30 px with explicit tooltips and keyboard accessibility names.
- Spacing: 12 px window inset, 7 px frame thickness; preserve the stream aspect ratio.

## States

Waiting instructions, system PIN confirmation, live video, no-frame pause, startup error, receiver restart and settings are explicit. The initial preview frame is iPhone 14 Pro and must never imply a detected device. Unknown model identifiers use the generic frame. Optional decorative cutouts can be disabled to avoid duplicate Islands and content occlusion.

## Reference fidelity

Keep the desktop visible around the shaped window. Toolbar contains minimize, close, always-on-top, size and settings controls; it does not pretend to provide remote iPhone input. Phone buttons and metallic edge are stylized geometry. The live Dynamic Island UI belongs to the iPhone stream; the local cutout is only a static decoration.
