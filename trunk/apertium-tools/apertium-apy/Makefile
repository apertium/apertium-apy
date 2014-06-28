langNames.db: tools/apertiumlangs.sql
	@if test -f unicode.db; then echo "WARNING: unicode.db now called langNames.db"; fi
	rm -f $@
	<$< sqlite3 $@
