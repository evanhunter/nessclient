# Developing
Use [pipenv](https://github.com/pypa/pipenv) to setup the local environment:

```sh
pipenv install --dev 
```

## Running tests

```sh
pipenv run python setup.py test
```

## Linting

```sh
pipenv run flake8 nessclient examples nessclient_tests docs *.py
pipenv run black  nessclient examples nessclient_tests docs *.py
```

## Type Checking

```sh
pipenv run mypy --strict nessclient examples nessclient_tests docs
```
