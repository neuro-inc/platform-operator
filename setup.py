from setuptools import find_packages, setup


install_requires = (
    "kopf==1.34.0",
    "aiohttp==3.7.4.post0",
    "pyyaml==5.4.1",
    "aiobotocore==1.4.1",
    "bcrypt==3.2.0",
    "neuro-logging==21.9",
)

setup(
    name="platform_operator",
    version="1.0.0",
    url="https://github.com/neuro-inc/platform-operator",
    packages=find_packages(),
    install_requires=install_requires,
    zip_safe=False,
)
