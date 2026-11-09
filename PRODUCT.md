# AirFrame

## Platform
adaptive — native desktop Windows first, macOS later.

## Confirmed scope
Receive the real iPhone screen through Control Centre > Screen Mirroring, without an iPhone companion app. The physical phone stays usable. Keep the receiver and its window alive across interruptions; iOS decides whether a locked phone preserves the session. No remote unlock.

## Appearance
User supplied a reference image of a compact floating phone-shaped window with a narrow dark toolbar, rounded metallic frame and Dynamic Island. This reference replaces the earlier sidebar proposal. Initial personal device: iPhone 14 Pro. Match frames to advertised device model where possible, remember manual corrections, adapt video aspect and orientation without cropping.

## Boundaries
AirPlay receiver handles Apple devices. Android needs a separate future receiver, not merely an Android skin. Do not claim Android reception. Do not infer an exact model from resolution alone. A decorative Island must be optional. Windows is the only platform being packaged now.

## Implementation choices
Prototype: PySide6/Qt desktop shell, modified UxPlay/GStreamer receiver in a child process. GPLv3 source and upstream notices included. Technical prototype before installer or stores.

## Confirmed hardware outcome
The user confirmed real iPhone screen reception. This does not establish audio, exact model identification, rotation, PIN behavior or lock/resume behavior.

## Optional experimental mouse
Explicitly enable the toolbar mouse feature, then pair the Windows PC from iPhone AssistiveTouch Bluetooth devices. No iPhone app or additional mouse/accessory is required. AirPlay supplies video; the PC Bluetooth LE peripheral adapter supplies relative HID mouse movement, clicks and dragging, with experimental wheel input. Capture requires live AirPlay and an eligible connected mouse peer; Escape returns control to the PC. A separate explicit experimental Home command attempts wake over a second encrypted Consumer report, even while video is absent and mouse input is suspended. Delivery does not prove physical wake. This is not coordinate touch, full keyboard control, authenticated unlock or AirPlay restart. iPhone pairing, actual input and wake response remain unverified. Retain receiver/window continuity across lock without promising automatic iOS reconnection.
