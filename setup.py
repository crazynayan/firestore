from setuptools import setup

setup(
    name='firestore-ci',
    version='1.0.0b1',
    packages=[''],
    url='github.com',
    license='MIT',
    author='Nayan Zaveri',
    author_email='nayan@crazyideas.co.in',
    description='ORM for Firestore with cascade',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7',
    ],
    keywords='firestore google orm cascade',
    install_requires='google-cloud-firestore',
    python_requires='>=3.5',
)
