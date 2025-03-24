from setuptools import find_packages, setup

with open('README.md', 'r') as f:
    long_description = f.read()


def get_version(path):
    with open(path) as f:
        for line in f:
            if line.startswith('__version__'):
                delim = '"' if '"' in line else "'"
                return line.split(delim)[1]
        raise RuntimeError('Unable to find version string.')


setup(
    name='django-computedfields',
    packages=find_packages(exclude=['example']),
    include_package_data=True,
    install_requires=[
        'Django>=4.2,<5.2',
        'typing_extensions>=4.1',
        'django-fast-update'
    ],
    version=get_version('computedfields/__init__.py'),
    license='MIT',
    description='autoupdated database fields for model methods',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='netzkolchose',
    author_email='j.breitbart@netzkolchose.de',
    url='https://github.com/netzkolchose/django-computedfields',
    download_url='https://github.com/netzkolchose/django-computedfields/archive/0.2.7.tar.gz',
    keywords=['django', 'method', 'decorator',
              'autoupdate', 'persistent', 'field'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Database',
        'Topic :: Database :: Front-Ends',
        'Topic :: Software Development :: Libraries',
        'Framework :: Django',
        'Framework :: Django :: 4.2',
        'Framework :: Django :: 5.0',
        'Framework :: Django :: 5.1',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12'
    ],
)
