from setuptools import setup, find_packages

setup(
    name="pypseudo",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'pytest>=6.0.0',
        'pytest-cov>=2.0.0',
        'pytest-json-report>=1.0.0',
        'astor>=0.8.0',
    ],
    entry_points={
        'console_scripts': [
            'pypseudo=pypseudo.cli.main:main',
        ],
    },
)