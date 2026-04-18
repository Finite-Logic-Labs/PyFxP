from setuptools import setup, find_packages, Extension
import sys

ext = []
if sys.platform.startswith("win"):
    ext += ["pyfxp/node.pyd", "pyfxp/graph.pyd", "pyfxp/rtlgen.pyd"]
else:
    ext += ["pyfxp/node.so", "pyfxp/graph.so", "pyfxp/rtlgen.so"]

setup(
    name='pyfxp',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        'numpy',
        'jinja2'
    ],
    test_suite='test',
    author='Your Name',
    author_email='your.email@example.com',
    description='Fixed-point design and analysis toolkit with Verilog codegen.',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.8',
    include_package_data=True,
    package_data={"pyfxp": ext},
)
