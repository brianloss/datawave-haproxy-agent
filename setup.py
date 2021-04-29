from setuptools import setup, find_packages
from os import path
this_directory = path.abspath(path.dirname(__file__))

with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='datawave_haproxy_agent',
    version='1.0.0',
    description='Datawave HAProxy Agent',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/brianloss/datawave-haproxy-agent',
    author='Brian Loss',
    author_email='brianloss@gmail.com',

    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],

    keywords='datawave haproxy agent load-balancer',

    packages=find_packages(),

    install_requires=['gevent', 'urllib3', 'PyYAML'],

    entry_points={"console_scripts": ["datawave-haproxy-agent=datawave_haproxy_agent.agent:main"]},
)