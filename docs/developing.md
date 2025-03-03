# Developing
Use [pipenv](https://github.com/pypa/pipenv) to setup the local environment:

```sh
pipenv install --dev 
```

## Running tests

```sh
pipenv run pytest
```

Generate test coverage information:
```sh
pipenv run coverage run -m pytest  && coverage html && coverage report --omit=setup.py --omit=.eggs
```

Run tests with logging output:
```sh
pipenv run pytest -s --log-cli-level=debug
```

Run a specific test with logging output:
```sh
pipenv run pytest -s --log-cli-level=debug nessclient_tests/test_client.py
```

## Command-line Interface
```sh
pipenv run python -m nessclient.cli <arguments>
```

## Examples
```sh
pipenv run python -m examples.listening_for_events
pipenv run python -m examples.sending_commands
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

## Generating Docs

```sh
pipenv run pip install -r docs/requirements.txt
pipenv run sphinx-build -b singlehtml -E -a docs/ docs/_build/
```

## Build Distributable

```sh
pipenv run python setup.py sdist bdist_wheel
```
