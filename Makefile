langNames.db: langNames.db
	python3	language_names/build_db.py	langNames.db
	@if test -f unicode.db; then echo "WARNING: unicode.db now called langNames.db"; fi

dist: langNames.db
	python3 setup.py sdist

release: langNames.db
	python3 setup.py sdist bdist_wheel
	twine upload --sign dist/*

test-release: langNames.db
	python3 setup.py sdist bdist_wheel
	twine upload --sign --repository-url https://test.pypi.org/legacy/ dist/*

test:
	flake8 *.py apertium_apy/ language_names/ tests/
	mypy --config-file mypy.ini **/*.py
	python3 -m unittest tests/test*.py
	coverage combine
	coverage report --fail-under 40

clean:
	rm -f langNames.db

distclean: clean
	rm -rf dist/ build/ *.egg-info/ .mypy_cache/ .coverage
