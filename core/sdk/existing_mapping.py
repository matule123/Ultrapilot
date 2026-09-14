"""Read-only Windows mapping. OpenFileMapping never creates an empty producer."""
import ctypes
import os


class ExistingMapping:
    def __init__(self, name, size):
        if os.name != 'nt':
            raise OSError('Windows named shared memory is unavailable')
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenFileMappingW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
        kernel.OpenFileMappingW.restype = wintypes.HANDLE
        kernel.MapViewOfFile.argtypes = (wintypes.HANDLE, wintypes.DWORD,
                                        wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t)
        kernel.MapViewOfFile.restype = ctypes.c_void_p
        kernel.UnmapViewOfFile.argtypes = (ctypes.c_void_p,)
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self._kernel, self._size, self._view = kernel, size, None
        self._handle = kernel.OpenFileMappingW(4, False, name)  # FILE_MAP_READ
        if not self._handle:
            raise OSError(ctypes.get_last_error(), 'Shared-memory producer is unavailable')
        self._view = kernel.MapViewOfFile(self._handle, 4, 0, 0, size)
        if not self._view:
            self.close()
            raise OSError(ctypes.get_last_error(), 'Cannot map shared-memory producer')

    def __getitem__(self, key):
        if not isinstance(key, slice) or key.step not in (None, 1):
            raise TypeError('Only bounded contiguous reads are supported')
        start, stop, _ = key.indices(self._size)
        if not self._view:
            raise OSError('Mapping is closed')
        return ctypes.string_at(self._view + start, max(0, stop-start))

    def close(self):
        if getattr(self, '_view', None):
            self._kernel.UnmapViewOfFile(self._view)
            self._view = None
        if getattr(self, '_handle', None):
            self._kernel.CloseHandle(self._handle)
            self._handle = None

    def __del__(self):
        self.close()
