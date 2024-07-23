from setuptools import setup
from __init__ import __program__, __version__

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name=__program__,
    version=__version__,
    author="Philip Orange",
    author_email="git@philiporange.com",
    description="A directory scanning tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/philiporange/lysergic",
    py_modules=["lysergic"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: CC0 1.0 Universal (CC0 1.0) Public Domain Dedication",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    python_requires=">=3.6",
    install_requires=[
        "tqdm",
    ],
    extras_require={
        "magika": ["magika"],
        "dev": ["black", "flake8"],
    },
    entry_points={
        "console_scripts": [
            "lsd=lysergic.lysergic:main",
        ],
    },
)
