from setuptools import find_packages, setup


install_requires = (
    "kopf==0.28.3",
    "aiohttp==3.7.3",
    "pyyaml==5.4.1",
    "aiobotocore==1.2.0",
)

setup(
    name="platform_operator",
    version="1.0.0",
    url="https://github.com/neuromation/platform-operator",
    packages=find_packages(),
    install_requires=install_requires,
    zip_safe=False,
)
