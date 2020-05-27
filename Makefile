SHELL:=/bin/bash

clean: clean-build clean-pyc

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	rm -fr .pytest_cache/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc: ## remove Python file artifacts
	rm -fr .pytest_cache/
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

install: clean ## install the package to the active Python's site-packages
	eval "$(pyenv init -)"
	python -m pip install -U pip
	python -m pip install -U webcolors
	python -m pip install -U funcparserlib
	python -m pip install -U setuptools==43.0.0
	python setup.py install

test: test-py2 test-py3
test-py2: test-setpy2 test-run
test-py3: test-setpy3 test-run
test-setpy3:
	eval "$(pyenv init -)"
	pyenv global 3.6.5
test-setpy2:
	eval "$(pyenv init -)"
	pyenv global 2.7.6
test-run: install
	eval "$(pyenv init -)"
	python -V
	python -m pytest

install-pytest:
	sudo apt-get install -y python-logilab-common
	eval "$(pyenv init -)"
	python -m pip install -U pip pytest==4.6.8 pytest-cov pytest-socket

install-pyenv:
	sudo apt-get install -y git
	rm -rf ~/.pyenv
	rm -f ~/bin/pyenv
	git clone https://github.com/pyenv/pyenv.git ~/.pyenv
	ln -s ~/.pyenv/bin/pyenv ~/bin/pyenv
	eval "$(pyenv init -)"
	pyenv install 2.7.6
	pyenv install 3.6.5


install-2.7.6: test-setpy2 install install-pytest
install-3.6.5: test-setpy3 install install-pytest

dependencies:
	sudo apt-get update -y
	sudo apt-get install -y \
		python-setuptools \
		build-essential \
		cython \
		python-dev \
		libxslt1-dev \
		libxml2-dev \
		zlib1g-dev \
		libevent-dev \
		libffi-dev \
		libfreetype6-dev \
		liblcms2-dev \
		cmake \
		imagemagick \
		libssl1.0-dev \
		libzmq3-dev \
		python-pip \
		libsqlite3-dev 

install-dev-env: dependencies install-pyenv install-3.6.5 install-2.7.6
	eval "$(pyenv init -)"
	pyenv global system
