
from setuptools import setup, find_packages

DEPENDENCIES = [
    "anthill-common"
]

setup(
    name='anthill-profile',
    package_data={
      "anthill.profile": ["anthill/profile/sql", "anthill/profile/static"]
    },
    setup_requires=["pypigit-version"],
    git_version="0.1.0",
    description='User profiles service for Anthill platform',
    author='desertkun',
    license='MIT',
    author_email='desertkun@gmail.com',
    url='https://github.com/anthill-platform/anthill-profile',
    namespace_packages=["anthill"],
    packages=find_packages(),
    zip_safe=False,
    install_requires=DEPENDENCIES
)
