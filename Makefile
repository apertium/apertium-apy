unicode.db: tools/apertiumlangs.sql
	rm $@
	<$< sqlite3 $@
