unicode.db: tools/apertiumlangs.sql
	rm -f $@
	<$< sqlite3 $@
