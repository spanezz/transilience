import pathlib

from setuptools import find_packages, setup

here = pathlib.Path(__file__).parent.resolve()
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="transilience",
    version="0.1.0.dev0",
    description="A provisioning library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/spanezz/transilience/",
    author="Enrico Zini",
    author_email="enrico@enricozini.org",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Topic :: System :: Systems Administration",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3 :: Only",
    ],
    packages=find_packages(where="."),
    python_requires=">=3.7, <4",
    install_requires=[
        # "coloredlogs", # Optional
        # "yapf", # Optional
        "jinja2",
        "mitogen",
        "PyYAML",
    ],
    extras_require={
        "device": ["parted"],
    },
)
