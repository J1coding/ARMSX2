"""Phase 4.2 Python guard: SettingsStore.init() MUST NOT touch any `.shared`
singleton transitively (depth >= 2), except for entries in the explicit
ALLOWLIST below.

Context: `.planning/debug/lc2-jit-hang-framepacing.md` (post-prior-fix
regression). The prior fix (uiupdatelink-crash.md) bounded its regression
test to ONE function (migrateFramePacingOptimalDefaultV1). The line-1827
sibling regression — SettingsStore.init() calling
FrameTimeDynamicResolutionController.shared.setEnabled, which reads
SettingsStore.shared.upscaleMultiplier — escaped that bounded test.

This guard GENERALIZES the prior test by walking the transitive call
graph rooted at SettingsStore.init() and forbidding ANY `*.shared`
access, with an explicit allowlist for paths verified safe by structural
argument.

Subsumes test_ios_frame_pacing_migration_no_shared_access.py (D-06) — the
four prior invariants are preserved verbatim in the test methods below.

Failure mode this guard prevents: a future contributor adds a new
`SomeSingleton.shared.foo()` call (or a transitive callee does so) inside
SettingsStore.init(). On iOS 26.x this deadlocks dispatch_once with
SIGTRAP "BUG IN CLIENT OF LIBDISPATCH"; on iOS 27 it crashes with SIGABRT
via doesNotRecognizeSelector against the partially-initialized instance.
Both failure modes are documented in the debug handoff docs cited above.
"""
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


class TestIosSettingsStoreInitNoSharedAccess(unittest.TestCase):
    """D-05 generalized regression test for SettingsStore.init() safety.

    7+ test methods: 4 D-06-preserved (verbatim from the prior
    test_ios_frame_pacing_migration_no_shared_access.py) + 3 D-05-new
    (init-body scan, Setting<T> onSet guard helper, D-01 wrapper) + 1
    transitive-callees scan that consumes the _walk_transitive_callees
    helper.
    """

    SETTINGS_STORE = REPO_ROOT / "platforms/ios/app/src/main/swift/Models/SettingsStore.swift"
    FRAME_PACING   = REPO_ROOT / "platforms/ios/app/src/main/swift/Models/SettingsStore+FramePacing.swift"
    FTDRC          = REPO_ROOT / "platforms/ios/app/src/main/swift/Models/FrameTimeDynamicResolutionController.swift"
    VPAD_SKIN_LIB  = REPO_ROOT / "platforms/ios/app/src/main/swift/Models/VPadSkinLibraryStore.swift"

    # ── ALLOWLIST (D-05) ────────────────────────────────────────────────
    # Each entry: (regex, justification). An entry MUST cite:
    #   (i)  a structural reason the access cannot deadlock, AND
    #   (ii) the test, table row, or invariant assertion that proves (i).
    # Future contributors who add a new `.shared` reference reachable from
    # init() must either restructure (preferred) or add an entry here with
    # the required justification. The allowlist is the escape hatch, not
    # the default.
    ALLOWLIST = [
        # (a) The Setting<T> onSet closure pattern: safe because Swift's
        # init-time observer suppression means didSet does NOT fire during
        # SettingsStore.init(), so the closures are never invoked from
        # that path. Verified by the D-03 invariant comment in Setting.swift
        # (struct Setting<Value> doc-comment block) and by
        # test_setting_onset_closures_use_guarded_helper below.
        (r"onSet:\s*\{\s*_\s+in\s+SettingsStore\.shared\.requestGraphicsApply(?:Guarded)?\(\)\s*\}",
         "Setting<T> onSet closures — not invoked during init per Swift observer-suppression rule "
         "(see Setting.swift CRITICAL note + SettingsStore.swift:1638-1643 reference template)"),

        # (b) D-01 deferral wrapper: FrameTimeDynamicResolutionController.shared.setEnabled
        # wrapped in DispatchQueue.main.async. Safe because the async dispatch
        # moves execution outside the swift_once body (next runloop tick).
        # Verified by test_line_1827_uses_deferral_wrapper below; see also
        # the CRITICAL note at SettingsStore.swift:~1827.
        (r"DispatchQueue\.main\.async\s*\{[^}]*FrameTimeDynamicResolutionController\.shared\.setEnabled",
         "FTDRC.setEnabled deferred via DispatchQueue.main.async (D-01) — see SettingsStore.swift "
         "CRITICAL note + .planning/debug/lc2-jit-hang-framepacing.md §Resolution"),

        # (c) VPadSkinLibraryStore.shared.adoptLegacySelection (init-body line ~1880;
        # flagged in RESEARCH.md §Summary discrepancy note 2 — NOT in the original
        # CONTEXT.md enumeration). Safe because VPadSkinLibraryStore.init body
        # (VPadSkinLibraryStore.swift:133-153) and adoptLegacySelection body
        # (lines 202-209) do NOT re-enter SettingsStore.shared. Verified by
        # singleton-safety table row 14 (produced by Plan 04 in 04.2-VERIFICATION.md).
        (r"VPadSkinLibraryStore\.shared\.adoptLegacySelection",
         "VPadSkinLibraryStore.shared — its init + adoptLegacySelection bodies do not re-enter "
         "SettingsStore.shared (singleton-safety table row 14 in 04.2-VERIFICATION.md)"),

        # (d) FTDRC.setEnabled's body internally reads
        # SettingsStore.shared.upscaleMultiplier (FrameTimeDynamicResolutionController.swift:116).
        # This is the re-entry point that caused the production deadlock.
        # Safe IFF the call site in SettingsStore.init() uses the D-01
        # DispatchQueue.main.async wrapper — by the time the deferred call
        # actually executes, swift_once for SettingsStore.shared has released
        # and the instance is fully initialized. Verified by
        # test_line_1827_uses_deferral_wrapper (which asserts the wrapper
        # is present at the only call site in init()).
        (r"SettingsStore\.shared\.upscaleMultiplier",
         "FTDRC.setEnabled body reads SettingsStore.shared.upscaleMultiplier — safe IFF the D-01 "
         "DispatchQueue.main.async wrapper is present at the call site (test_line_1827_uses_deferral_wrapper)"),
    ]

    def setUp(self):
        self.assertTrue(
            self.SETTINGS_STORE.exists(),
            "SettingsStore.swift missing — REPO_ROOT resolution is wrong",
        )
        self.assertTrue(
            self.FRAME_PACING.exists(),
            "SettingsStore+FramePacing.swift missing — REPO_ROOT resolution is wrong",
        )
        self.assertTrue(
            self.FTDRC.exists(),
            "FrameTimeDynamicResolutionController.swift missing — REPO_ROOT resolution is wrong",
        )
        self.assertTrue(
            self.VPAD_SKIN_LIB.exists(),
            "VPadSkinLibraryStore.swift missing — REPO_ROOT resolution is wrong",
        )
        self.settings_store = self.SETTINGS_STORE.read_text(encoding="utf-8")
        self.frame_pacing   = self.FRAME_PACING.read_text(encoding="utf-8")
        self.ftdrc          = self.FTDRC.read_text(encoding="utf-8")
        self.vpad_skin_lib  = self.VPAD_SKIN_LIB.read_text(encoding="utf-8")

    # ── Body-extraction helpers (regex-based; tree_sitter_swift NOT installed) ──

    def _extract_init_body(self) -> str:
        """Pull the body of `private init()` from SettingsStore.swift.

        Uses brace-matching at column 4 (the class-body indentation level).
        Line-number-independent per RESEARCH.md Pitfall 5.
        """
        m = re.search(
            r"(?m)^    private init\(\) \{(?P<body>.*?)^    \}\n",
            self.settings_store,
            re.DOTALL,
        )
        self.assertIsNotNone(
            m,
            "Could not locate `private init()` in SettingsStore.swift — "
            "was it renamed, removed, or re-indented?",
        )
        return m.group("body")

    def _extract_migrate_function_body(self) -> str:
        """Pull the body of `static func migrateFramePacingOptimalDefaultV1()`.

        (Copied verbatim from the prior test — D-06 subsumption contract.)
        """
        # Match the function declaration and its body up to the matching closing
        # brace at column 4 (the extension's indentation level).
        m = re.search(
            r"(?m)^    static func migrateFramePacingOptimalDefaultV1\(\) \{(?P<body>.*?)^    \}\n",
            self.frame_pacing,
            re.DOTALL,
        )
        self.assertIsNotNone(
            m,
            "Could not locate `static func migrateFramePacingOptimalDefaultV1()` "
            "in SettingsStore+FramePacing.swift — was it renamed or removed?",
        )
        return m.group("body")

    def _strip_line_comments(self, text: str) -> str:
        """Remove `// ...` line comments from Swift source.

        (Copied verbatim from the prior test — D-06 subsumption contract.)

        The migration function legitimately mentions `SettingsStore.shared` in
        its docstring / explanatory comments (explaining WHY the reference is
        forbidden). We want to flag only ACTIVE code references, so we strip
        `//` comments before regex matching.
        """
        out_lines = []
        for line in text.splitlines():
            # Strip everything from the first `//` to end of line. (Swift has no
            # multi-line `/* */` comments inside this function body; if any are
            # added later they should be stripped too — out of scope here.)
            idx = line.find("//")
            if idx >= 0:
                line = line[:idx]
            out_lines.append(line)
        return "\n".join(out_lines)

    def _walk_transitive_callees(self, init_body: str, depth: int = 2):
        """Walk function calls from init_body transitively to `depth` levels.

        Mechanism: pure-regex per RESEARCH.md recommendation
        (tree_sitter_swift NOT installed; pure-regex matches existing
        project convention — see TESTING.md §iOS guards).

        Returns a list of (callee_file_label, callee_name, callee_body)
        tuples whose bodies can be scanned for forbidden `.shared`
        references.

        For each `Self.foo()` / `X.shared.foo()` call found in init_body,
        locate the callee body in the appropriate source file and recurse.
        Depth-limited to avoid combinatorial blow-up; the actual
        SettingsStore.init() call graph is shallow (mostly
        ARMSX2Bridge.getINI* + the few .shared sites).

        Unknown callees (e.g., enum-namespace static methods like
        BackgroundStorage.migrateLegacyBackgroundsIfNeeded, or ARMSX2Bridge
        C++ bridging statics) are silently skipped — they have no Swift
        body to scan, and a hazard in them would not be a Swift init-safety
        issue.
        """
        seen = set()  # (owner, callee_name) tuples already visited
        results = []

        # Source-file lookup table keyed by the type that owns the callee.
        # Self.* lookups search SettingsStore.swift first (instance methods)
        # then SettingsStore+FramePacing.swift (the migrateFramePacing*
        # extension methods live there).
        owner_files = [
            ("SettingsStore+FramePacing", self.frame_pacing),
            ("SettingsStore", self.settings_store),
            ("FrameTimeDynamicResolutionController", self.ftdrc),
            ("VPadSkinLibraryStore", self.vpad_skin_lib),
        ]

        def find_callee_body(callee_name: str):
            """Return (file_label, body) for a Swift func named callee_name.

            Tries both `    static func <name>(...) { body }` and
            `    func <name>(...) { body }` shapes, indented at column 4
            (the type-body / extension-body level). Returns ("", "") if
            no match in any indexed file.
            """
            for file_label, src in owner_files:
                for prefix in (r"    static\s+func\s+", r"    func\s+"):
                    pat = (
                        r"(?m)^" + prefix + re.escape(callee_name)
                        + r"\s*(?:<[^>]*>)?\s*\([^)]*\)"
                        r"(?:\s*->\s*[^{]+?)?\s*\{(?P<body>.*?)^    \}\n"
                    )
                    m = re.search(pat, src, re.DOTALL)
                    if m:
                        return file_label, m.group("body")
            return "", ""

        def walk(body: str, current_depth: int):
            if current_depth > depth:
                return
            # Self.foo() — Swift static method call on the current type.
            for m in re.finditer(r"\bSelf\s*\.\s*([a-zA-Z_]\w*)\s*\(", body):
                callee = m.group(1)
                key = ("Self", callee)
                if key in seen:
                    continue
                seen.add(key)
                file_label, callee_body = find_callee_body(callee)
                if callee_body:
                    results.append((file_label, f"Self.{callee}", callee_body))
                    walk(callee_body, current_depth + 1)
            # X.shared.foo() — cross-singleton method call.
            for m in re.finditer(
                r"\b([A-Z]\w*)\s*\.\s*shared\s*\.\s*([a-zA-Z_]\w*)\s*\(", body
            ):
                owner, callee = m.group(1), m.group(2)
                key = (owner, callee)
                if key in seen:
                    continue
                seen.add(key)
                file_label, callee_body = find_callee_body(callee)
                if callee_body:
                    label = file_label or owner
                    results.append((label, f"{owner}.shared.{callee}", callee_body))
                    walk(callee_body, current_depth + 1)

        walk(init_body, current_depth=1)
        return results

    def _assert_no_unallowed_shared(self, body: str, scope: str):
        """For each `*.shared` token in `body`, verify that at least one
        ALLOWLIST regex matches a context window containing the token.

        Used by both the init-body scan and the transitive-callees scan.
        The window is +/- 400 chars around the token — wide enough to
        capture the wrapping DispatchQueue.main.async { ... } block and
        the surrounding structural context, narrow enough to avoid
        matching unrelated allowlist entries elsewhere in the body.
        """
        for match in re.finditer(r"([A-Z]\w*)\s*\.\s*shared(?:\.[a-zA-Z_]\w*)?", body):
            token = match.group(0)
            window_start = max(0, match.start() - 400)
            window_end = min(len(body), match.end() + 400)
            window = body[window_start:window_end]
            covered = any(re.search(pat, window) for pat, _ in self.ALLOWLIST)
            line_in_scope = body[:match.start()].count("\n") + 1
            self.assertTrue(
                covered,
                f"{scope} references `{token}` at line +{line_in_scope} with no "
                f"ALLOWLIST entry covering its context window. To permit this "
                f"access, add an ALLOWLIST entry with (i) a structural "
                f"justification (why this access cannot deadlock) and (ii) a "
                f"test/table-row citation proving the justification holds. "
                f"See ALLOWLIST comments for the D-05 policy."
            )

    # ── D-06 subsumption contract: 4 prior invariants, preserved verbatim ──

    def test_migration_function_does_not_reference_settings_store_shared(self):
        """The migration function MUST NOT touch SettingsStore.shared in any form.

        It runs inside SettingsStore.init() (which is itself running inside the
        swift_once / dispatch_once body of the `static let shared` initializer).
        Touching SettingsStore.shared re-enters that in-flight once-token and
        deadlocks dispatch_once on iOS 26.x (SIGTRAP) or produces
        doesNotRecognizeSelector on iOS 27 (SIGABRT).
        """
        body = self._strip_line_comments(self._extract_migrate_function_body())
        forbidden_patterns = [
            (r"SettingsStore\s*\.\s*shared", "SettingsStore.shared"),
            (r"Self\s*\.\s*shared", "Self.shared"),
            (r"\.shared\s*\.\s*applyFramePacingPreset", ".shared.applyFramePacingPreset"),
            (r"\bshared\s*\.\s*applyFramePacingPreset", "shared.applyFramePacingPreset"),
        ]
        for pattern, label in forbidden_patterns:
            self.assertNotRegex(
                body,
                pattern,
                f"migrateFramePacingOptimalDefaultV1() must not reference {label} — "
                "it runs inside SettingsStore.init() and would recursively re-enter "
                "the in-flight swift_once token, deadlocking (iOS 26.x SIGTRAP) or "
                "crashing with doesNotRecognizeSelector (iOS 27 SIGABRT). See "
                ".planning/debug/uiupdatelink-crash.md.",
            )

    def test_migration_function_writes_optimal_table_directly_to_ini(self):
        """When the migration applies Optimal, it must write the D-01 Optimal
        table values directly to INI (not via applyFramePacingPreset).

        This guards the symmetric-invariant: the migration must NOT silently
        become a no-op for the optimal case. The six D-01 Optimal values are
        VsyncQueueSize=4, OutputLatencyMS=15, BufferMS=50,
        SyncToHostRefreshRate=false, NominalScalar=1.0 (encoding targetFPS=60
        + frameLimiterEnabled=true).
        """
        body = self._extract_migrate_function_body()
        required_writes = [
            (r'"EmuCore/GS"[\s\S]*?"VsyncQueueSize"[\s\S]*?value:\s*4', "VsyncQueueSize=4"),
            (r'"SPU2/Output"[\s\S]*?"OutputLatencyMS"[\s\S]*?value:\s*15', "OutputLatencyMS=15"),
            (r'"SPU2/Output"[\s\S]*?"BufferMS"[\s\S]*?value:\s*50', "BufferMS=50"),
            (r'"EmuCore/GS"[\s\S]*?"SyncToHostRefreshRate"[\s\S]*?value:\s*false', "SyncToHostRefreshRate=false"),
            (r'"Framerate"[\s\S]*?"NominalScalar"[\s\S]*?value:\s*1\.0', "NominalScalar=1.0"),
        ]
        for pattern, label in required_writes:
            self.assertRegex(
                body,
                pattern,
                f"migrateFramePacingOptimalDefaultV1() must write D-01 Optimal table value "
                f"{label} directly to INI. Without these writes, the migration would not "
                "actually apply the Optimal preset (it used to delegate to "
                "SettingsStore.shared.applyFramePacingPreset, which is now forbidden).",
            )

    def test_migration_is_called_at_top_of_init(self):
        """SettingsStore.init() MUST call migrateFramePacingOptimalDefaultV1()
        BEFORE any stored-property assignment that reads from INI.

        Ordering rationale: the migration writes new INI values for the Optimal
        preset case. If it runs AFTER init() has already read those INI keys
        into stored properties, the stored properties will be stale. Running it
        at the top of init() (immediately after the `suppressINIWrites = true`
        guard) ensures all subsequent stored-property reads see the
        post-migration INI state.
        """
        # Extract the init() body.
        m = re.search(
            r"(?m)^    private init\(\) \{(?P<body>.*?)^    \}\n",
            self.settings_store,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "Could not locate `private init()` in SettingsStore.swift")
        init_body = m.group("body")

        # Locate the migration call.
        migration_call_re = re.compile(r"Self\s*\.\s*migrateFramePacingOptimalDefaultV1\s*\(\s*\)")
        migration_match = migration_call_re.search(init_body)
        self.assertIsNotNone(
            migration_match,
            "SettingsStore.init() must call Self.migrateFramePacingOptimalDefaultV1() — "
            "without it, fresh installs never get the D-02 Optimal-preset migration.",
        )

        # The first ARMSX2Bridge.getINI* call AFTER the migration call is fine —
        # but no ARMSX2Bridge.getINI* call may PRECEDE the migration call (other
        # than inside comments). To keep the test robust, we just check that the
        # migration call appears BEFORE the first stored-property assignment
        # that uses ARMSX2Bridge.getINI*.
        first_getini_match = re.search(r"ARMSX2Bridge\.getINI", init_body)
        if first_getini_match is None:
            self.skipTest("No ARMSX2Bridge.getINI* reads in init() — nothing to order against")

        self.assertLess(
            migration_match.start(),
            first_getini_match.start(),
            "Self.migrateFramePacingOptimalDefaultV1() must be called BEFORE the first "
            "ARMSX2Bridge.getINI* read in SettingsStore.init(), so subsequent stored-"
            "property reads see the post-migration INI values. See "
            ".planning/debug/uiupdatelink-crash.md.",
        )

    def test_init_does_not_call_migrate_twice(self):
        """There must be exactly one call to migrateFramePacingOptimalDefaultV1
        inside SettingsStore.init(). A duplicate call (e.g. left behind by a
        botched edit) would either re-trigger the write path or, worse,
        re-introduce a recursive-access hazard if a future contributor puts the
        migration back at the bottom of init().
        """
        matches = re.findall(
            r"Self\s*\.\s*migrateFramePacingOptimalDefaultV1\s*\(\s*\)",
            self.settings_store,
        )
        self.assertEqual(
            len(matches),
            1,
            f"SettingsStore.swift must contain exactly one call to "
            f"Self.migrateFramePacingOptimalDefaultV1(); found {len(matches)}.",
        )

    # ── D-05 new invariants (the generalization) ──

    def test_init_body_has_no_unallowed_shared_access(self):
        """D-05: SettingsStore.init() body MUST NOT contain any `*.shared`
        access except where a context window around the token is covered
        by an ALLOWLIST entry. Each allowlist entry carries a structural
        justification and a test/table-row citation.

        Today this passes because the only two .shared references in the
        init body are (1) the D-01-wrapped FrameTimeDynamicResolutionController.shared.setEnabled
        call and (2) VPadSkinLibraryStore.shared.adoptLegacySelection — both
        in the seed allowlist. A new `FooBar.shared.baz()` call would have
        no allowlist entry covering its window and would fail loudly.
        """
        body = self._strip_line_comments(self._extract_init_body())
        self._assert_no_unallowed_shared(body, "SettingsStore.init() body")

    def test_setting_onset_closures_use_guarded_helper(self):
        """D-04: All Setting<T> onSet closures call requestGraphicsApplyGuarded,
        not the raw requestGraphicsApply. Belt-and-braces — the closures
        are not reachable from init() (Swift observer suppression), but
        the central helper is the second layer of defense.

        The closures are not invoked during SettingsStore.init() because
        Swift's init-time observer suppression means didSet does not fire
        on init-body assignments. The requestGraphicsApplyGuarded() helper
        (which checks suppressINIWrites) is belt-and-braces: if a future
        refactor breaks the observer-suppression invariant (e.g., a
        convenience init that mutates a property after delegation), the
        suppressINIWrites check prevents the call from descending into
        requestGraphicsApply() and the downstream GS pipeline reload.
        """
        closures = re.findall(
            r"onSet:\s*\{\s*_\s+in\s+SettingsStore\.shared\.(requestGraphicsApply(?:Guarded)?)\(\)\s*\}",
            self.settings_store,
        )
        # Lower-bound assertion (per RESEARCH.md Pitfall 1: do NOT hard-code
        # the exact closure count — the test forbids .shared reachability
        # from init, not closure count).
        self.assertGreaterEqual(
            len(closures), 1,
            "SettingsStore.swift must define at least one Setting<T> onSet closure "
            "of the form `onSet: { _ in SettingsStore.shared.requestGraphicsApply... }` "
            "— the absence of any such closure likely means the Setting<T> pattern "
            "has been refactored away and this test should be revisited."
        )
        for method_name in closures:
            self.assertEqual(
                method_name, "requestGraphicsApplyGuarded",
                "All Setting<T> onSet closures must call requestGraphicsApplyGuarded "
                "(not the raw requestGraphicsApply). The guard checks "
                "suppressINIWrites — true for the duration of SettingsStore.init() — "
                "and prevents the closure from descending into the graphics-apply "
                "debounce if it is ever invoked during init. See "
                "platforms/ios/app/src/main/swift/Models/Setting.swift CRITICAL note."
            )

    def test_line_1827_uses_deferral_wrapper(self):
        """D-01: The FrameTimeDynamicResolutionController.shared.setEnabled call
        in init() MUST be wrapped in DispatchQueue.main.async { ... }.

        Method name retained for historical context — the test does NOT
        depend on line numbers (per RESEARCH.md Pitfall 5); it pattern-matches
        the init body extracted via brace-matching. The line-1827 reference
        is the original bug site; the actual line may drift as the file
        evolves, but the invariant is structural.

        Mechanism: locate every `FrameTimeDynamicResolutionController.shared.setEnabled`
        reference in the init body and verify each has a `DispatchQueue.main.async`
        opener in the preceding 200 chars with no intervening closing brace
        (which would indicate we have exited a wrapper).
        """
        init_body = self._extract_init_body()

        # Positive: at least one wrapper must exist (the bootstrap call).
        wrapper_re = re.compile(
            r"DispatchQueue\.main\.async\s*\{[^}]*?"
            r"FrameTimeDynamicResolutionController\.shared\.setEnabled",
            re.DOTALL,
        )
        self.assertRegex(
            init_body, wrapper_re,
            "D-01: SettingsStore.init() must wrap the "
            "FrameTimeDynamicResolutionController.shared.setEnabled bootstrap "
            "call in `DispatchQueue.main.async { ... }`. Without the deferral, "
            "setEnabled reads SettingsStore.shared.upscaleMultiplier "
            "(FrameTimeDynamicResolutionController.swift:116) synchronously, "
            "re-entering the in-flight swift_once token and deadlocking "
            "dispatch_once: iOS 26.x (SIGTRAP 'BUG IN CLIENT OF LIBDISPATCH'), "
            "iOS 27 (SIGABRT via doesNotRecognizeSelector). See "
            ".planning/debug/lc2-jit-hang-framepacing.md §Resolution."
        )

        # Negative: every setEnabled reference must be inside a wrapper.
        # Variable-length lookbehind is unsupported in Python's `re` module
        # (re.error: look-behind requires fixed-width pattern), so we use
        # a manual window check: scan the preceding 200 chars for the most
        # recent `DispatchQueue.main.async` opener with no intervening `}`
        # that would indicate we have already exited a wrapper.
        bare_re = re.compile(r"FrameTimeDynamicResolutionController\.shared\.setEnabled")
        bare_matches = list(bare_re.finditer(init_body))
        self.assertGreaterEqual(
            len(bare_matches), 1,
            "Test invariant: SettingsStore.init() must call "
            "FrameTimeDynamicResolutionController.shared.setEnabled at least "
            "once (the bootstrap that starts the Adaptive Resolution controller "
            "from its persisted INI value)."
        )
        for m in bare_matches:
            preceding = init_body[max(0, m.start() - 200):m.start()]
            last_open = preceding.rfind("DispatchQueue.main.async")
            last_brace_close = preceding.rfind("}")
            wrapper_open_present = (
                last_open != -1 and last_open > last_brace_close
            )
            self.assertTrue(
                wrapper_open_present,
                "D-01 violation: FrameTimeDynamicResolutionController.shared.setEnabled "
                "in SettingsStore.init() is NOT inside a DispatchQueue.main.async { ... } "
                "wrapper. The bare synchronous form deadlocks dispatch_once on iOS 26.x "
                "(SIGTRAP 'BUG IN CLIENT OF LIBDISPATCH') or crashes via "
                "doesNotRecognizeSelector on iOS 27 (SIGABRT). See "
                ".planning/debug/lc2-jit-hang-framepacing.md §Resolution."
            )

    def test_init_transitive_callees_have_no_unallowed_shared_access(self):
        """D-05 transitive check: walk SettingsStore.init()'s call graph to
        depth 2 and verify each callee body is either clean of `.shared`
        references OR covered by an ALLOWLIST entry.

        This is the load-bearing transitive check. The init-body scan
        alone would have missed the original bug — the deadlock is at
        FrameTimeDynamicResolutionController.setEnabled's body (which
        reads SettingsStore.shared.upscaleMultiplier), reached transitively
        from init. Today this passes because (a) Self.migrateFramePacingOptimalDefaultV1's
        body is clean of .shared references (closed by the prior
        uiupdatelink-crash.md fix), (b) FTDRC.setEnabled's body's
        .shared reference is in the allowlist (entry (d) — safe IFF the
        D-01 wrapper is present, verified by test_line_1827_uses_deferral_wrapper),
        and (c) VPadSkinLibraryStore.adoptLegacySelection's body is clean
        of .shared references (singleton-safety table row 14).

        Sanity assertion: the walk must find at least the
        migrateFramePacingOptimalDefaultV1 callee — if it doesn't, the
        walk mechanism is broken and the test is silently a no-op.
        """
        init_body = self._extract_init_body()
        callees = self._walk_transitive_callees(init_body, depth=2)

        callee_names = [name for _, name, _ in callees]
        self.assertTrue(
            any("migrateFramePacingOptimalDefaultV1" in name for name in callee_names),
            f"Transitive walk did not find Self.migrateFramePacingOptimalDefaultV1 — "
            f"the walk mechanism is broken or the migration function was renamed. "
            f"Found callees: {callee_names}"
        )

        for file_label, name, body in callees:
            stripped = self._strip_line_comments(body)
            self._assert_no_unallowed_shared(
                stripped,
                f"transitive callee `{name}` (body in {file_label}.swift)"
            )


if __name__ == "__main__":
    unittest.main()
