// Setting.swift — configuration-only property wrapper for INI-backed settings
// SPDX-License-Identifier: GPL-3.0+

import Foundation

/// Configuration-only: holds the INI section/key/writer for a setting. The
/// @Observable macro owns the stored property; didSet consults this config.
///
/// CRITICAL: `onSet` is invoked from each property's `didSet` (e.g., the
/// `upscaleMultiplier` property's didSet in SettingsStore.swift). Swift's
/// init-time observer-suppression rule means `didSet` does NOT fire during
/// `SettingsStore.init()` body assignments — so `onSet` is never reached
/// from that path. If a future change to `Setting<Value>` semantics or to
/// `SettingsStore.init()` structure causes `onSet` to fire during init
/// (e.g., a `convenience init` that mutates a property after delegation),
/// the 22 closures that reference
/// `SettingsStore.shared.requestGraphicsApplyGuarded()` (the graphics-pipeline Settings; see the
/// `requestGraphicsApplyGuarded()` docstring in SettingsStore.swift for the
/// exhaustive list)
/// would re-enter the in-flight `swift_once` token and deadlock
/// `dispatch_once` on iOS 26.x (SIGTRAP "BUG IN CLIENT OF LIBDISPATCH") or
/// produce `doesNotRecognizeSelector` on iOS 27 (SIGABRT). Guarded by
/// `test_ios_settingsstore_init_no_shared_access.py` and the
/// `requestGraphicsApplyGuarded()` helper.
struct Setting<Value> {
    let section: String
    let key: String
    let defaultValue: Value
    let suppressible: Bool
    let writer: (String, String, Value) -> Void
    let onSet: ((Value) -> Void)?

    init(section: String,
         key: String,
         default defaultValue: Value,
         suppressible: Bool = true,
         writer: @escaping (String, String, Value) -> Void,
         onSet: ((Value) -> Void)? = nil) {
        self.section = section
        self.key = key
        self.defaultValue = defaultValue
        self.suppressible = suppressible
        self.writer = writer
        self.onSet = onSet
    }
}
