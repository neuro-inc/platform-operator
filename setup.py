from setuptools import find_packages, setup


install_requires = (
    "kopf==0.27rc5",
    "aiohttp==3.6.2",
    "pyyaml==5.3.1",
    "idna==2.8",
    "aiobotocore==1.0.4",
)

setup(
    name="platform_operator",
    version="1.0.0",
    url="https://github.com/neuromation/platform-operator",
    packages=find_packages(),
    install_requires=install_requires,
    zip_safe=False,
)
