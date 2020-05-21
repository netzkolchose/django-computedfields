from setuptools import setup, find_packages

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name='django-computedfields',
    packages=find_packages(exclude=['example']),
    include_package_data=True,
    install_requires=[],
    version='0.0.19',
    license='MIT',
    description='autoupdated database fields for model methods',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='netzkolchose',
    author_email='j.breitbart@netzkolchose.de',
    url='https://github.com/netzkolchose/django-computedfields',
    download_url='https://github.com/netzkolchose/django-computedfields/archive/0.0.19.tar.gz',
    keywords=['django', 'method', 'decorator', 'autoupdate', 'persistent', 'field'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Database',
        'Topic :: Database :: Front-Ends',
        'Topic :: Software Development :: Libraries',
        'Framework :: Django',
        'Framework :: Django :: 2.2',
        'Framework :: Django :: 3.0',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8'
    ],
)
