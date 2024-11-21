import setuptools


setuptools.setup(
    name='fsspec_disk',
    version='1.0.0',
    author='RimoChan',
    author_email='the@librian.net',
    description='fsspec_disk',
    long_description=open('readme.md', encoding='utf8').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/RimoChan/fsspec_disk',
    packages=[
        'fsspec_disk',
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent',
    ],
    install_requires=[
        'winfspy>=0.8.4',
        's3fs>=2024.10.0',
        'fsspec>=2024.10.0',
    ],
)
