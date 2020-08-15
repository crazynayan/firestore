from os import path

from setuptools import setup, find_packages

this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="firestore-ci",
    version="2020.8.15",
    url="https://github.com/crazynayan/firestore",
    packages=find_packages(),
    license="MIT",
    author="Nayan Zaveri",
    author_email="nayan@crazyideas.co.in",
    description="ORM for Firestore with cascade",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.7",
    ],
    keywords="firestore google orm cascade",
    install_requires="google-cloud-firestore",
    python_requires=">=3.5",
)
