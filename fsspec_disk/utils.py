from fsspec.spec import AbstractFileSystem


class CacheInfoFileSystem:
    def __init__(self, fs: AbstractFileSystem):
        self._info_cache = {}
        self._fs = fs

    def info(self, path):
        if path not in self._info_cache:
            try:
                self._info_cache[path] = self._fs.info(path)
            except FileNotFoundError:
                self._info_cache[path] = 'not found'
        if self._info_cache[path] == 'not found':
            raise FileNotFoundError()
        else:
            return self._info_cache[path]

    def _magic(k):
        def _f(self, path, *t, **d):
            self._info_cache.pop(path, None)
            return getattr(self._fs, k)(path, *t, **d)
        return _f

    def _magic2(k):
        def _f(self, file_name, new_file_name, *t, **d):
            self._info_cache.pop(file_name, None)
            self._info_cache.pop(new_file_name, None)
            return getattr(self._fs, k)(file_name, new_file_name, *t, **d)
        return _f

    def open(self, path, mode, *t, **d):
        if mode in ['r', 'rb']:
            return self._fs.open(path, mode, *t, **d)
        self._info_cache.pop(path, None)
        o = self._fs.open(path, mode, *t, **d)
        _close = o.close
        def 假close():
            r = _close()
            self._info_cache.pop(path, None)
            return r
        o.close = 假close
        return o

    mkdir = _magic('mkdir')
    rm = _magic('rm')
    touch = _magic('touch')
    mv_file = _magic2('mv_file')
    mv = _magic2('mv')

    def __getattr__(self, k):
        return getattr(self._fs, k)
