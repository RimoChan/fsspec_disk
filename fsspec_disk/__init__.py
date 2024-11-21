import io
import logging
import datetime
from threading import Lock
from types import FunctionType
from typing import Tuple, List
from pathlib import Path

import fsspec

from winfspy import (
    FileSystem,
    BaseFileSystemOperations,
    FILE_ATTRIBUTE,
    CREATE_FILE_CREATE_OPTIONS,
    NTStatusObjectNameNotFound,
    NTStatusObjectNameCollision,
)
from winfspy.plumbing.win32_filetime import filetime_now
from winfspy.plumbing.security_descriptor import SecurityDescriptor


SD = SecurityDescriptor.from_string("O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;WD)")


class FalseOpen:
    def __init__(self, file_name, create_options, granted_access):
        self.file_name = file_name
        self.create_options = create_options
        self.granted_access = granted_access

    def close(self):
        None

    def __repr__(self):
        return f'<FalseOpen {repr(self.file_name)}>'


class Barbarossa(BaseFileSystemOperations):
    def __init__(self, fsspec_system: fsspec.AbstractFileSystem, use_elf_mkdir=False, log=True, volume_label='fsspec_disk'):
        super().__init__()
        self.fsspec_system = fsspec_system
        self.log = log
        self.use_elf_mkdir = use_elf_mkdir
        self._opened_files = []
        self._locks = {}
        self._lock_lock = Lock()
        self._volume_label = volume_label

    def _get_lock(self, file_name):
        with self._lock_lock:
            if file_name not in self._locks:
                self._locks[file_name] = Lock()
            return self._locks[file_name]

    def list_opened_files(self):
        self._opened_files = [i for i in self._opened_files if i.closed]
        return self._opened_files

    def _replace_name(self, file_name):
        file_name = file_name.replace('\\', '/')
        if file_name != '/':
            file_name = file_name.removeprefix('/')
        return file_name

    def _get_info(self, file_name):
        file_name = self._replace_name(file_name)
        try:
            return self.fsspec_system.info(file_name)
        except FileNotFoundError:
            if file_name == '/':
                return {
                    'name': '/',
                    'type': 'directory',
                }
            raise NTStatusObjectNameNotFound()

    def _fs_info_to_file_info(self, info: dict):
        def _get_float(key: str):
            value = info.get('created', 0)
            if isinstance(value, datetime.datetime):
                value = value.timestamp()
            return value
        return {
            "file_name": info['name'],
            "file_attributes": FILE_ATTRIBUTE.FILE_ATTRIBUTE_DIRECTORY if info['type'] == 'directory' else FILE_ATTRIBUTE.FILE_ATTRIBUTE_NORMAL,
            "allocation_size": info.get('size') or 0,
            "file_size": info.get('size') or 0,
            "creation_time": int(_get_float('created')*10000000)+116444736000000000,
            "last_access_time": int(_get_float('mtime')*10000000)+116444736000000000,
            "last_write_time": int(_get_float('mtime')*10000000)+116444736000000000,
            "change_time": int(_get_float('mtime')*10000000)+116444736000000000,
            "index_number": 0,
        }

    def _open(self, file_name, *args):
        file_name = self._replace_name(file_name)
        o = self.fsspec_system.open(file_name, *args)
        o.file_name = file_name
        return o

    def get_security(self, file_context):
        return SD

    def get_security_by_name(self, file_name) -> Tuple:
        return (
            self._fs_info_to_file_info(self._get_info(file_name))['file_attributes'],
            SD.handle,
            SD.size,
        )

    def read_directory(self, file_context, marker) -> List:
        entries = [self._fs_info_to_file_info(info) for info in self.fsspec_system.ls(file_context.file_name, detail=True)]
        for entry in [*entries]:
            entry["file_name"] = entry["file_name"].replace('\\', '/').split('/')[-1]
            if entry["file_name"] == 'elf':
                entries.remove(entry)
        if file_context.file_name != '/':
            entries.extend([{"file_name": "."}, {"file_name": ".."}])
        entries = sorted(entries, key=lambda x: x["file_name"])
        if marker is None:
            return entries
        for i, entry in enumerate(entries):
            if entry["file_name"] == marker:
                return entries[i + 1 :]
        logging.error(f'找不到marker={marker}，entries={[e["file_name"] for e in entries]}')
        return entries

    def can_delete(self, file_context, file_name: str) -> None:
        None

    def set_security(self, file_context, security_information, modification_descriptor):
        None

    def create(
        self,
        file_name,
        create_options,
        granted_access,
        file_attributes,
        security_descriptor,
        allocation_size,
    ):
        file_name = self._replace_name(file_name)
        if self.fsspec_system.exists(file_name):
            raise NTStatusObjectNameCollision()
        if create_options & CREATE_FILE_CREATE_OPTIONS.FILE_DIRECTORY_FILE:
            self.fsspec_system.mkdir(file_name)
            if self.use_elf_mkdir:
                self.fsspec_system.touch(f'{file_name}/elf')
            return FalseOpen(file_name, create_options, granted_access)
        else:
            self.fsspec_system.touch(file_name)
            return self._open(file_name, 'wb')

    def rename(self, file_context, file_name, new_file_name, replace_if_exists):
        file_name = self._replace_name(file_name)
        new_file_name = self._replace_name(new_file_name)
        file_context.close()
        try:
            self.fsspec_system.mv_file(file_name, new_file_name, recursive=True)
        except Exception as e:
            self.fsspec_system.mv(file_name, new_file_name, recursive=True)

    def set_file_size(self, file_context, new_size, set_allocation_size):
        None

    def write(self, file_context, buffer, offset, write_to_end_of_file, constrained_io):
        assert not write_to_end_of_file
        assert not constrained_io
        if getattr(file_context, 'loc', None) != offset:
            file_context.seek(offset)
        file_context.write(bytes(buffer))
        return len(buffer)

    def overwrite(self, file_context, file_attributes, replace_file_attributes: bool, allocation_size: int) -> None:
        try:
            file_context.truncate(0)
            file_context.seek(0)
        except io.UnsupportedOperation:
            self.fsspec_system.touch(file_context.file_name)

    # https://learn.microsoft.com/en-us/windows/win32/wmisdk/file-and-directory-access-rights-constants
    def open(self, file_name, create_options, granted_access):
        file_name = self._replace_name(file_name)
        是文件夹 = file_name == '\\' or create_options & CREATE_FILE_CREATE_OPTIONS.FILE_DIRECTORY_FILE
        是文件 = create_options & CREATE_FILE_CREATE_OPTIONS.FILE_NON_DIRECTORY_FILE
        if not 是文件夹 and not 是文件:
            if self.fsspec_system.isfile(file_name):
                是文件 = True
            else:
                是文件夹 = True
        if 是文件夹:
            return FalseOpen(file_name, create_options, granted_access)
        elif 是文件:
            if granted_access & 1 and granted_access & 2:
                mode = 'r+b'
            elif granted_access & 1:
                mode = 'rb'
            elif granted_access & 2:
                mode = 'ab'
            else:
                return FalseOpen(file_name, create_options, granted_access)
        return self._open(file_name, mode)

    def cleanup(self, file_context, file_name, flags) -> None:
        file_context.close()
        FspCleanupDelete = 0x01
        if flags & FspCleanupDelete:
            self.fsspec_system.rm(file_context.file_name, recursive=True)

    def get_volume_info(self):
        return {
            "total_size": 2 ** 30,
            "free_size": 2 ** 30,
            "volume_label": self._volume_label,
        }

    def get_file_info(self, file_context) -> dict:
        import time; time.sleep(0.01)
        return self._fs_info_to_file_info(self._get_info(file_context.file_name))

    def set_basic_info(self, file_context, file_attributes, creation_time, last_access_time, last_write_time, change_time, file_info):
        return self._fs_info_to_file_info(self._get_info(file_context.file_name))

    def read(self, file_context, offset: int, length: int) -> bytes:
        file_context.seek(offset, 0)
        return file_context.read(length)

    # python cleanup
    def close(self, file_context):
        None


for k, v in [*Barbarossa.__dict__.items()]:
    if k[0] != '_' and isinstance(v, FunctionType):
        def 新f(self, *args, _k=k, _v=v):
            try:
                res = _v(self, *args)
            except Exception as e:
                res = e.__class__.__name__
                raise
            finally:
                if self.log:
                    if len(str(res)) < 1000:
                        print(f'{_k}{str(args)} -> {res}')
                    else:
                        print(f'{_k}{str(args)}')
            return res
        setattr(Barbarossa, k, 新f)


def fsspec_disk(mountpoint: str, fsspec_system: fsspec.AbstractFileSystem, **kwargs):
    mountpoint = Path(mountpoint)
    is_drive = mountpoint.parent == mountpoint
    reject_irp_prior_to_transact0 = not is_drive

    operations = Barbarossa(fsspec_system, **kwargs)
    fs = FileSystem(
        str(mountpoint),
        operations,
        sector_size=512,
        sectors_per_allocation_unit=1,
        volume_creation_time=filetime_now(),
        volume_serial_number=0,
        file_info_timeout=1000,
        case_sensitive_search=1,
        case_preserved_names=1,
        unicode_on_disk=1,
        persistent_acls=1,
        post_cleanup_when_modified_only=1,
        um_file_context_is_user_context2=1,
        file_system_name=str(mountpoint),
        reject_irp_prior_to_transact0=reject_irp_prior_to_transact0,
    )
    return fs
