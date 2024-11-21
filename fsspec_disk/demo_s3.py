import time
import fire

from fsspec.implementations.dirfs import DirFileSystem
from fsspec.implementations.cached import SimpleCacheFileSystem
import s3fs

from fsspec_disk import fsspec_disk
from fsspec_disk.utils import CacheInfoFileSystem


def ember(bucket, endpoint_url, key, secret, volume_label='fsspec_disk'):
    s3 = CacheInfoFileSystem(
        SimpleCacheFileSystem(fs=DirFileSystem(path=bucket, fs=s3fs.S3FileSystem(endpoint_url=endpoint_url, key=key, secret=secret)))
    )
    fs = fsspec_disk('u:', s3, use_elf_mkdir=True, log=False, volume_label=volume_label)
    try:
        fs.start()
        while True:
            time.sleep(1)
    finally:
        fs.stop()


if __name__ == '__main__':
    fire.Fire(ember)
