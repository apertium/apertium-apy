langNames.db: language_names/scraped.sql language_names/scraped-sil.sql language_names/manual.sql language_names/variants.sql
	@if test -f unicode.db; then echo "WARNING: unicode.db now called langNames.db"; fi
	rm -f $@
	cat $^ | sqlite3 $@

dist: langNames.db
	python3 setup.py sdist

release: langNames.db
	python3 setup.py sdist bdist_wheel upload --sign

test-release: langNames.db
	python3 setup.py sdist bdist_wheel upload --repository https://test.pypi.org/legacy/ --sign

test:
	flake8 **/*.py
	mypy --config-file mypy.ini **/*.py
	coverage run --source apertium_apy -m unittest tests/test*.py
	coverage report --fail-under 20

clean:
	rm -f langNames.db

distclean: clean
	rm -rf dist/ build/ *.egg-info/ .mypy_cache/ .coverage
