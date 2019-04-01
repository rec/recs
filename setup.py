from setuptools import setup
import recs

_classifiers = [
    'Development Status :: 4 - Beta',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Programming Language :: Python :: 3.7',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Topic :: Software Development :: Libraries',
    'Topic :: Utilities',
]

setup(name='recs',
      version=recs.__version__,
      author='Tom Ritchford',
      author_email='tom@swirly.com',
      url='https://github.com/rec/recs',
      tests_require=['pytest'],
      py_modules=['recs'],
      description='Try to import all modules below a given root',
      long_description=open('README.rst').read(),
      license='MIT',
      classifiers=_classifiers,
      keywords=['testing', 'importing'],
      )
