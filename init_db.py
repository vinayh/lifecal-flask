import sqlite3

connection = sqlite3.connect('database.db')

with open('schema.sql') as f:
    connection.executescript(f.read())

cur = connection.cursor()

cur.execute("INSERT INTO entries (start, category, note) VALUES (?, ?, ?)",
            ('2023-09-11', 1, 'Content of entry with category 1'))

cur.execute("INSERT INTO entries (start, category, note) VALUES (?, ?, ?)",
            ('2023-09-04', 3, 'Content of entry with category 3'))

connection.commit()
connection.close()