import sys

for filename in sys.argv[1:]:
    with open(filename, 'r+') as f:
        header = f.readline()
        reader = f.readlines()
        reader.sort()
        f.truncate(0)
        f.seek(0)
        f.write(header)
        for i in reader:
            f.write(i)
