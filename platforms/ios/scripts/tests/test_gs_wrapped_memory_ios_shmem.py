import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]  # repository root
GS_CPP = ROOT / "pcsx2/GS/GS.cpp"


def _non_windows_branch_body(source: str) -> str:
    # The non-Windows GSAllocateWrappedMemory begins after the Windows block
    # closes with "#else" near the bottom of the Windows-only helpers and ends
    # at the next top-level function (GSFreeWrappedMemory) or #endif.
    match = re.search(
        r"(?ms)^void\* GSAllocateWrappedMemory\(size_t size, size_t repeat\)\n\{(.*?)(?=^void GSFreeWrappedMemory\()",
        source,
    )
    # If there are two matches (Windows + POSIX), we want the LAST one.
    matches = list(re.finditer(
        r"(?ms)^void\* GSAllocateWrappedMemory\(size_t size, size_t repeat\)\n\{(.*?)(?=^void GSFreeWrappedMemory\()",
        source,
    ))
    assert matches, "GSAllocateWrappedMemory body not found in pcsx2/GS/GS.cpp"
    return matches[-1].group(1)


def _non_windows_free_body(source: str) -> str:
    matches = list(re.finditer(
        r"(?ms)^void GSFreeWrappedMemory\(void\* ptr, size_t size, size_t repeat\)\n\{(.*?)^\}",
        source,
    ))
    assert matches, "GSFreeWrappedMemory body not found in pcsx2/GS/GS.cpp"
    return matches[-1].group(1)


class GSWrappedMemoryIOSShmemTests(unittest.TestCase):
    """Regression guard for the iOS game-launch GS shmem abort.

    Root cause (verified from LiveContainer-2026-07-18-153408.ips, binary UUID
    5F29F60B-A11F-3D7E-85F5-8F49FF22C9CD): GSAllocateWrappedMemory's POSIX
    branch called shm_open("/GS.mem", O_RDWR|O_CREAT|O_EXCL, 0600) directly,
    which the iOS sandbox rejects, returning -1 and propagating nullptr up to
    GSLocalMemory::GSLocalMemory() where pxFailRel("Failed to allocate GS
    memory storage.") aborted the process on the GS thread. The rest of the
    codebase routes shared-memory creation through HostSys::CreateSharedMemory
    (common/Linux/LnxHostSys.cpp:136), which contains an iOS file-backed
    fallback (CreateIOSFileBackedSharedMemory, lines 81-133). These tests
    enforce that GSAllocateWrappedMemory delegates to that helper instead of
    reinventing the shm_open path.
    """

    def test_gs_allocate_wrapped_memory_does_not_call_shm_open_directly(self):
        source = GS_CPP.read_text(encoding="utf-8")
        body = _non_windows_branch_body(source)
        # The POSIX branch must NOT contain a bare shm_open call. The Android
        # memfd_create path is fine; we are only forbidding the POSIX shm_open
        # that iOS rejects.
        self.assertNotRegex(
            body,
            r"\bshm_open\s*\(",
            "GSAllocateWrappedMemory POSIX branch must not call shm_open directly; "
            "route through HostSys::CreateSharedMemory to get the iOS file-backed fallback.",
        )

    def test_gs_allocate_wrapped_memory_uses_host_sys_create_shared_memory(self):
        source = GS_CPP.read_text(encoding="utf-8")
        body = _non_windows_branch_body(source)
        self.assertRegex(
            body,
            r"HostSys::CreateSharedMemory\s*\(",
            "GSAllocateWrappedMemory POSIX branch must obtain its fd via "
            "HostSys::CreateSharedMemory so the iOS TMPDIR file-backed fallback applies.",
        )

    def test_gs_allocate_wrapped_memory_preserves_repeat_mirroring_mmap_loop(self):
        source = GS_CPP.read_text(encoding="utf-8")
        body = _non_windows_branch_body(source)
        # The PS2 GS memory model requires the same backing fd to be mapped
        # `repeat` times at consecutive virtual addresses. Whatever refactor
        # routes through HostSys::CreateSharedMemory must preserve this loop.
        self.assertRegex(
            body,
            r"for\s*\(\s*size_t\s+i\s*=\s*1\s*;\s*i\s*<\s*repeat\s*;\s*i\+\+\s*\)",
            "GSAllocateWrappedMemory must retain the for (i=1; i<repeat; i++) "
            "MAP_FIXED mmap mirroring loop.",
        )
        self.assertRegex(
            body,
            r"MAP_SHARED\s*\|\s*MAP_FIXED",
            "GSAllocateWrappedMemory must retain a MAP_SHARED | MAP_FIXED mmap "
            "of the shared backing fd at each mirror offset.",
        )

    def test_gs_free_wrapped_memory_uses_host_sys_destroy_shared_memory(self):
        source = GS_CPP.read_text(encoding="utf-8")
        body = _non_windows_free_body(source)
        self.assertRegex(
            body,
            r"HostSys::DestroySharedMemory\s*\(",
            "GSFreeWrappedMemory POSIX branch must release its fd via "
            "HostSys::DestroySharedMemory to match the create path.",
        )

    def test_gs_allocate_wrapped_memory_logs_failure_without_abort(self):
        source = GS_CPP.read_text(encoding="utf-8")
        body = _non_windows_branch_body(source)
        # On allocation failure, the function must still return nullptr to the
        # caller (GSLocalMemory::GSLocalMemory) so the caller's own contract
        # (the pxFailRel) remains the single point of abort. The allocator
        # itself must not call pxFailRel/abort/pxOnAssertFail directly.
        self.assertRegex(
            body,
            r"return\s+nullptr\s*;",
            "GSAllocateWrappedMemory must return nullptr on allocation failure "
            "(the caller's assertion handles the abort).",
        )
        self.assertNotRegex(
            body,
            r"\b(pxFailRel|pxOnAssertFail|abort)\s*\(",
            "GSAllocateWrappedMemory must not abort the process directly; "
            "return nullptr and let GSLocalMemory::GSLocalMemory() decide.",
        )


if __name__ == "__main__":
    unittest.main()
