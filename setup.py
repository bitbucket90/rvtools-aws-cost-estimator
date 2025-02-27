#!/usr/bin/env python3
"""Setup script for the RVTools to AWS Cost Estimator package."""

from setuptools import setup, find_packages

setup(
    name="rv2aws",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "boto3",
        "pandas",
        "openpyxl",
        "reportlab",
    ],
    entry_points={
        "console_scripts": [
            "rv2aws=rv2aws.main:main",
        ],
    },
    author="Brandon Pendleton",
    author_email="brandon.pendleton@ahead.com",
    description="RVTools to AWS Migration Cost Estimator",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/bitbucket90/rvtools-aws-cost-estimator",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
)