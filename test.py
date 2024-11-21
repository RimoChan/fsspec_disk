import os
import time
import random
import shutil
from pathlib import Path

from fsspec.implementations.local import LocalFileSystem
from fsspec.implementations.dirfs import DirFileSystem
from fsspec.implementations.cached import SimpleCacheFileSystem
from fsspec.implementations.memory import MemoryFileSystem
from fsspec.implementations.local import LocalFileOpener
from fsspec.implementations.zip import ZipFileSystem

from fsspec_disk import fsspec_disk
from fsspec_disk.utils import CacheInfoFileSystem


disk = 't'

temp_dir = Path(__file__).parent.absolute() / 'temp'
os.makedirs(temp_dir, exist_ok=True)


def test(
    fsspec_system,
    use_elf_mkdir=False,
    log=True,
    assert_size=True,
    need_sleep_on_write=False,
    need_sleep_on_remove=False,
):
    def _sleep(t='write'):
        if t == 'write' and need_sleep_on_write:
            time.sleep(3)
        if t == 'remove' and need_sleep_on_remove:
            print('sleep!')
            time.sleep(3)
    fssd = fsspec_disk(mountpoint=f'{disk}:', fsspec_system=fsspec_system, use_elf_mkdir=use_elf_mkdir, log=log)
    fssd.start()
    try:
        x = random.randint(1000, 9999)
        for test_dir in [f'{disk}:/test_dir_{x}', f'{disk}:/test_dddir_{x}/test_dddir_{x}/']:
            os.makedirs(test_dir, exist_ok=True)

            assert Path(f'{test_dir}/1.txt').exists() == False
            assert len(os.listdir(f'{test_dir}')) == 0

            with open(f'{test_dir}/1.txt', 'w') as a:
                assert len(os.listdir(f'{test_dir}')) == 1
                a.write('123')
            _sleep()
            assert open(f'{test_dir}/1.txt', 'r').read() == '123'
            Path(f'{test_dir}/2.txt').touch()
            _sleep()
            assert len(os.listdir(f'{test_dir}')) == 2

            a = open(f'{test_dir}/1.txt', 'a')
            a.write('456')
            a.close()
            assert open(f'{test_dir}/1.txt', 'r').read() == '123456'
            if assert_size:
                assert os.stat(f'{test_dir}/1.txt').st_size == 6
            open(f'{test_dir}/1.txt', 'w').close()
            assert open(f'{test_dir}/1.txt', 'r').read() == ''
            if assert_size:
                assert os.stat(f'{test_dir}/1.txt').st_size == 0

            assert Path(f'{test_dir}/1.txt').exists() == True
            assert Path(f'{test_dir}/1.txt').is_file() == True
            assert Path(f'{test_dir}/1.txt').is_dir() == False
            os.remove(f'{test_dir}/1.txt')
            _sleep('remove')
            assert Path(f'{test_dir}/1.txt').exists() == False
            assert Path(f'{test_dir}/1.txt').is_file() == False
            assert Path(f'{test_dir}/1.txt').is_dir() == False

            for i in [1, 100, 10000, 1000000]:
                with open(f'{test_dir}/3.txt', 'wb') as a:
                    a.write(b'123'*i)
                if assert_size:
                    print('什么情况', fssd.operations.list_opened_files())
                    assert os.stat(f'{test_dir}/3.txt').st_size == 3 * i
                # exit()
            assert len(os.listdir(f'{test_dir}')) == 2
            os.rename(f'{test_dir}/3.txt', f'{test_dir}/33.txt')
            _sleep('remove')
            assert len(os.listdir(f'{test_dir}')) == 2
            os.remove(f'{test_dir}/33.txt')

            assert len(os.listdir(f'{test_dir}')) == 1

            shutil.rmtree(f'{test_dir}/')

            assert Path(f'{test_dir}').exists() == False
        print('好！', fsspec_system)
    finally:
        fssd.stop()


if __name__ == '__main__':
    test(DirFileSystem(path=temp_dir, fs=LocalFileSystem()))

    test(SimpleCacheFileSystem(fs=DirFileSystem(path=temp_dir, fs=LocalFileSystem())), assert_size=False)

    test(MemoryFileSystem())

    test(SimpleCacheFileSystem(fs=MemoryFileSystem()))
