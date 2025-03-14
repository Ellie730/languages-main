CREATE TABLE users (id INTEGER NOT NULL PRIMARY KEY, 
username TEXT, 
hash TEXT, 
language TEXT, 
card_order TEXT,
new_cards TEXT,
deck_order TEXT,
time TEXT);

CREATE TABLE decks (deck_id INTEGER NOT NULL PRIMARY KEY,
language TEXT NOT NULL,
name TEXT NOT NULL,
author TEXT,
date TEXT, 
medium TEXT,
genre TEXT,
size TEXT,
creator TEXT NOT NULL,
public TEXT NOT NULL);

CREATE TABLE words (id INTEGER NOT NULL PRIMARY KEY,
language TEXT NOT NULL,
word TEXT NOT NULL,
definition TEXT NOT NULL,
part TEXT NOT NULL,
common TEXT,
frequency TEXT);

CREATE TABLE deck_contents (deck_id INTEGER NOT NULL,
word_id INTEGER NOT NULL,
frequency INTEGER NOT NULL);

CREATE TABLE users_to_decks (user_id INTEGER NOT NULL,
deck_id INTEGER NOT NULL,
progress REAL,
position INTEGER NOT NULL, 
weighted REAL);

CREATE TABLE user_progress (user_id INTEGER NOT NULL,
word_id INTEGER NOT NULL,
due INTEGER,
interval INTEGER,
viewings INTEGER,
easy INTEGER,
good INTEGER,
okay INTEGER,
some INTEGER,
none INTEGER,
state TEXT, 
frequency TEXT);