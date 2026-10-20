"""macOS Keychain adapter. Secrets never enter shell arguments or plaintext files."""

import ctypes as c
import platform

SERVICE = b"ai.the-godfather.worker"
ACCOUNT = b"machine-credential-v1"
NOT_FOUND = -25300


class Keychain:
    def __init__(self) -> None:
        if platform.system() != "Darwin":
            raise OSError("macOS Keychain is available only on a Mac")
        self.api = c.CDLL("/System/Library/Frameworks/Security.framework/Security")
        self.cf = c.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.cf.CFRelease.argtypes = [c.c_void_p]
        self.cf.CFRelease.restype = None
        self.api.SecKeychainFindGenericPassword.argtypes = [
            c.c_void_p,
            c.c_uint32,
            c.c_char_p,
            c.c_uint32,
            c.c_char_p,
            c.POINTER(c.c_uint32),
            c.POINTER(c.c_void_p),
            c.POINTER(c.c_void_p),
        ]
        self.api.SecKeychainAddGenericPassword.argtypes = [
            c.c_void_p,
            c.c_uint32,
            c.c_char_p,
            c.c_uint32,
            c.c_char_p,
            c.c_uint32,
            c.c_void_p,
            c.POINTER(c.c_void_p),
        ]
        self.api.SecKeychainItemFreeContent.argtypes = [c.c_void_p, c.c_void_p]
        self.api.SecKeychainItemDelete.argtypes = [c.c_void_p]
        for name in (
            "SecKeychainFindGenericPassword",
            "SecKeychainAddGenericPassword",
            "SecKeychainItemFreeContent",
            "SecKeychainItemDelete",
        ):
            getattr(self.api, name).restype = c.c_int32

    def read(self) -> str | None:
        length, pointer = c.c_uint32(), c.c_void_p()
        status = self.api.SecKeychainFindGenericPassword(
            None,
            len(SERVICE),
            SERVICE,
            len(ACCOUNT),
            ACCOUNT,
            c.byref(length),
            c.byref(pointer),
            None,
        )
        if status == NOT_FOUND:
            return None
        if status != 0:
            raise OSError("Unlock your login Keychain and allow The Godfather Worker access")
        try:
            return c.string_at(pointer, length.value).decode("utf-8")
        finally:
            self.api.SecKeychainItemFreeContent(None, pointer)

    def write(self, value: str) -> None:
        # Never replace an identity implicitly, including after ambiguous enrollment.
        raw = value.encode("utf-8")
        status = self.api.SecKeychainAddGenericPassword(
            None,
            len(SERVICE),
            SERVICE,
            len(ACCOUNT),
            ACCOUNT,
            len(raw),
            raw,
            None,
        )
        if status != 0:
            raise OSError(
                "Could not save identity in Keychain; revoke this pending Mac and reconnect"
            )

    def delete(self) -> None:
        item = c.c_void_p()
        status = self.api.SecKeychainFindGenericPassword(
            None,
            len(SERVICE),
            SERVICE,
            len(ACCOUNT),
            ACCOUNT,
            None,
            None,
            c.byref(item),
        )
        if status == NOT_FOUND:
            return
        if status != 0:
            raise OSError("Could not access the worker identity in Keychain")
        try:
            if self.api.SecKeychainItemDelete(item) != 0:
                raise OSError("Could not remove the worker identity from Keychain")
        finally:
            self.cf.CFRelease(item)
