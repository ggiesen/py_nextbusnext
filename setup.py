from setuptools import find_packages
from setuptools import setup

with open("README.md", "r") as readme:
    long_description = readme.read()

setup(
    name="py_nextbusnext",
    version="2.3.0",
    author="ViViDboarder",
    description="Minimalistic Python client for the NextBus public API for real-time transit "
    "arrival data",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/vividboarder/py_nextbus",
    packages=find_packages(
        exclude=[
            "build",
            "dist",
            "tests",
        ]
    ),
    python_requires=">=3.10",
    install_requires=[
        "requests",
        "ua-generator",
    ],
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
