import sqlite3

from collections import Counter
from datetime import datetime
from flask import Flask, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, presence, update, lemmatise

languages = ["German", "Italian", "Spanish", "Finnish", "French"]

app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.secret_key = "plumbingfailure"

with app.app_context():  
    con = sqlite3.connect("languagecards.db", check_same_thread=False)
    db = con.cursor()


@app.route("/")
@login_required
def index():

    update()
    
    db.execute(
    """SELECT * FROM decks JOIN users_to_decks ON decks.deck_id = users_to_decks.deck_id 
    WHERE user_id = ? AND decks.language = ?"""
    , (session["user_id"], session["language"]))
    decks = db.fetchall()
    for deck in decks:
        
        db.execute("""UPDATE users_to_decks SET size = (SELECT COUNT(*) FROM deck_contents WHERE deck_id = ? AND NOT word_id IN 
                   (SELECT word_id FROM user_progress WHERE state = 'blacklisted' AND user_id = ?)) WHERE deck_id = ?""", (deck[0], session["user_id"], deck[0]))
        con.commit()
        db.execute("""SELECT size FROM users_to_decks WHERE deck_id = ? AND user_id = ?""", (deck[0], session["user_id"]))
        size = db.fetchall()[0][0]
        if size == "0" or size is None:
            size = 1
        db.execute("""SELECT COUNT (*) FROM user_progress WHERE (state = 'learning' OR state = 'learned' OR state = 'known') AND user_id = ? 
        AND word_id IN (SELECT word_id FROM deck_contents WHERE deck_id = ?)""",
        (session["user_id"], deck[0]))
        known = db.fetchall()[0][0]
        db.execute("""SELECT SUM (frequency) FROM user_progress 
        WHERE user_id = ? AND NOT state = 'blacklisted' AND word_id IN 
        (SELECT word_id FROM deck_contents WHERE deck_id = ?)""", (session["user_id"], deck[0]))
        frequency = db.fetchall()[0][0]
        if frequency is None or frequency == "0":
            frequency = 1
        db.execute ("""SELECT SUM (frequency) FROM user_progress 
        WHERE (state = 'learning' OR state = 'learned' OR state = 'known') AND user_id = ? AND word_id IN 
        (SELECT word_id FROM deck_contents WHERE deck_id = ?)""", (session["user_id"], deck[0]))
        weighted = db.fetchall()[0][0]
        if weighted is None:
            weighted = 0
        db.execute("""UPDATE users_to_decks SET progress = ?, weighted = ? 
        WHERE deck_id = ? AND user_id = ?""", (round(known/int(size), 2), round(weighted/frequency, 2), deck[0], session["user_id"]))
        con.commit()
    db.execute("SELECT * FROM decks JOIN users_to_decks ON decks.deck_id = users_to_decks.deck_id WHERE user_id = ? AND language = ? ORDER BY position", (session["user_id"], session["language"]))
    display = db.fetchall()
    count = len(display) - 1
    return render_template ("mainpage.html", display = display, user = session["user_id"], count = count)



@app.route("/add_deck", methods=["POST"])
@login_required
def add_deck():

    #see if the deck is already added
    deck = request.form.get("deck")
    db.execute("""SELECT deck_id FROM users_to_decks WHERE deck_id = ? AND user_id = ?""", (deck, session["user_id"]))
    try:
        a = db.fetchall()[0][0]
        return redirect("/search_decks")
    
    #if not add to utd, with the right number in position
    except IndexError:

        db.execute("""SELECT COUNT(*) FROM users_to_decks WHERE user_id = ?""", (session["user_id"],))
    count = db.fetchall()[0][0]

    db.execute("""INSERT INTO users_to_decks (user_id, deck_id, position) VALUES (?, ?, ?)""", (session["user_id"], deck, count))

    db.execute("""SELECT * FROM deck_contents WHERE deck_id = ?""", (deck,))
    contents =  db.fetchall()

    #loop by word
    for i in range(len(contents)):

        #if not in user_progress, insert
        db.execute("""SELECT * FROM user_progress WHERE word_id = ? AND user_id = ?""", (contents[i][1], session["user_id"]))
        presence = db.fetchall()
        if len(presence) == 0:

            db.execute("""INSERT INTO user_progress (user_id, word_id, interval, viewings, easy, good, okay, some, none, state, frequency) 
                       VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 'new', ?)""", (session["user_id"], contents[i][1], contents[i][2]))
        #else update the frequency value
        else:
            frequency = int(presence[0][11]) + int(contents[i][2])
            db.execute("""UPDATE user_progress SET frequency = ? WHERE user_id = ? AND word_id = ?""", (frequency, session["user_id"], contents[i][1]))

    con.commit()
    return redirect("/search_decks")



@app.route("/blacklist", methods=["POST"])
@login_required
def blacklist():

    source = request.form.get("confirmed")
    if source == "0":
        
        #if confirmed, create entry to balcklist the person
        db.execute("""INSERT INTO blacklist (user_id, creator) VALUES (?, ?)""", (session["user_id"], session["creator"]))
        db.execute("""UPDATE user_progress SET alternate = NULL WHERE user_id = ? 
                   AND word_id IN (SELECT original FROM alternates WHERE creator = ?)""", 
                   (session["user_id"], session["creator"]))
        con.commit()
        return redirect ("/review")
    
    else:

        # get the information needed for the user to decide whether to blacklist this creator
        session["creator"] = request.form.get("creator")
        if session["creator"] == session["user_id"]:
            return render_template ("blacklist_failed.html")
        
        db.execute("""SELECT COUNT (*) FROM alternates 
                   JOIN user_progress ON user_progress.word_id = alternates.original
                   WHERE user_id = ? AND alternates.alternate = user_progress.alternate AND alternates.creator = ?""",
                   (session["user_id"], session["creator"]))
        count = db.fetchall()[0][0]
        db.execute("""SELECT username FROM users WHERE id = ?""", (session["creator"],))
        creator = db.fetchall()[0][0]
        return render_template ("confirm_blacklist.html", count = count, creator = creator)



@app.route("/change_language")
@login_required
def change_language():

    language = request.args.get("language")
    session["language"] = language
    db.execute ("UPDATE users SET language = ? WHERE id = ?", (language, session["user_id"]))
    con.commit()
    return redirect("/")



@app.route("/change_status", methods=["POST"])
@login_required
def change_status():
    status = request.form.get("status")
    id = request.form.get("deck_id")
    if status == "Public":
        db.execute ("UPDATE decks SET status = private WHERE deck_id = ?", (id,))
    if status == "Private":
        db.execute ("UPDATE decks SET status = public WHERE deck_id = ?", (id,))
    con.commit()
    return redirect ("/")



@app.route("/choose_alternate", methods=["GET", "POST"])
@login_required
def choose_alternate():

    if request.method == "POST":
    #get the values of the selected alternate from the last 
        alt = request.form.get("choice")

        #insert into the database
        db.execute("""UPDATE user_progress SET alternate = ? WHERE user_id = ? AND word_id = ?""", (alt, session["user_id"], session["card"]))
        con.commit()
        return redirect ("/review")
    else:

        db.execute("""SELECT word FROM words WHERE id = ?""", (session["card"],))
        card = db.fetchall()[0][0]
        db.execute("SELECT * FROM alternates WHERE original = ? AND NOT creator IN (SELECT creator FROM blacklist WHERE user_id = ?)", (session["card"], session["user_id"]))
        alternates = db.fetchall()
        return render_template ("choose_alternate.html", card = card, alternates = alternates)



@app.route("/custom_study", methods=["POST"])
@login_required
def custom_study():
    
    if request.method == "POST":

        number = int(request.form.get("number"))
        session[session["language"]]["new_seen"] -= number
        session.modified = True
        return redirect ("/review")




@app.route("/edit_deck", methods=["POST"])
@login_required
def edit_deck():

    # check if the current user is the creator of the deck 
    deck = request.form.get("deck_id")
    db.execute ("SELECT creator FROM decks WHERE deck_id = ?", (deck,))
    creator = db.fetchall()[0][0]

    #else make a new deck that contains the same info, to be edited
    db.execute ("SELECT * FROM decks WHERE deck_id = ?", (deck,))
    deck_info = db.fetchall()
    db.execute ("""INSERT INTO decks (language, name, medium, genre, author, date, size, creator, public) values (?,?,?,?,?,?,?,?, 'private')"""
    , (session["language"], deck_info[0][2], deck_info[0][5], deck_info[0][6], deck_info[0][3], deck_info[0][4], deck_info[0][7], session["user_id"]))
    db.execute("SELECT * FROM users_to_decks WHERE user_id = ? AND deck_id = ?", (session["user_id"], deck))
    user_info = db.fetchall()
    db.execute("SELECT deck_id FROM decks WHERE name = ? AND creator = ?", (deck_info[0][2], session["user_id"]))
    temp = db.fetchall()
    edited_id = temp[len(temp) - 1][0]
    db.execute ("""INSERT INTO users_to_decks (user_id, deck_id, progress, position, weighted) VALUES (?,?,?,?,?)"""
    , (session["user_id"], edited_id, user_info[0][2], user_info[0][3], user_info[0][4]))
    db.execute ("DELETE FROM users_to_decks WHERE user_id = ? AND deck_id = ?", (session["user_id"], deck))
    #copy cards from old deck into new
    db.execute("""INSERT INTO temp (deck_id, word_id, frequency) SELECT deck_id, word_id, frequency FROM deck_contents WHERE deck_id = ?""", (deck,))
    db.execute("""UPDATE temp SET deck_id = ?""", (edited_id,))
    db.execute("""INSERT INTO deck_contents (deck_id, word_id, frequency) SELECT deck_id, word_id, frequency FROM temp""")
    db.execute("""DELETE FROM temp""")
    con.commit()
    session["deck_id"] = edited_id
    
    return redirect ("/input")



@app.route("/input", methods=["GET", "POST"])
@login_required
def input():
        
    if request.method == "POST":
        
        text = request.form.get("input")

        # lemmatise each word and get a list of words and their frequencies
        lemmatised = lemmatise(text, session["language"])
        contents = Counter(lemmatised)

        # create list of all words that have been created already 
        existing = []
        db.execute("SELECT word FROM words WHERE language = ?", (session["language"],))
        created = db.fetchall()
        for word in created:
            existing.append(word[0])
        
        #create a list of all words in this deck
        db.execute("""SELECT word_id FROM deck_contents WHERE deck_id = ?""", (session["deck_id"],))
        deck_words = db.fetchall()
        deck_contents = []
        for word in deck_words:
            deck_contents.append(word[0])
        
        #create a list of the user's words
        db.execute("""SELECT word_id FROM user_progress WHERE user_id = ? AND word_id IN (
        SELECT word_id FROM words WHERE language = ?)""", (session["user_id"], session["language"]))
        uwords = db.fetchall()
        user_words = []
        for word in uwords:
            user_words.append(word[0])

        #for each word, if it is new create a card. 

        for word in contents.keys():
            if word in existing:

                # TODO: rework deck updates
                # if the word is not in this deck, add it to the deck
                db.execute ("SELECT id FROM words WHERE word = ? AND language = ?", (word, session["language"]))
                word_id = db.fetchall()[0][0]
                if word_id not in deck_contents:
                    db.execute("INSERT INTO deck_contents (deck_id, word_id, frequency) VALUES (?,?,?)", (session["deck_id"], word_id, contents[word]))
                # if the word is in the deck, add the frequency value
                else:
                    db.execute ("SELECT frequency FROM deck_contents WHERE word_id = ?", (word_id,))
                    frequency = db.fetchall()[0][0] + contents[word]
                    db.execute ("UPDATE deck_contents SET frequency = ? WHERE word_id = ?", (frequency, word_id))
                
                # add the card to user_progress or update frequency
                if word_id not in user_words:
                    db.execute ("""INSERT INTO user_progress 
                    (user_id, word_id, viewings, easy, good, okay, some, none, state, frequency) VALUES
                    (?,?,0,0,0,0,0,0,'new',?)""", (session["user_id"], word_id, contents[word]))
                else:
                    db.execute("""SELECT frequency FROM user_progress WHERE user_id = ? AND word_id = ?""",
                    (session["user_id"], word_id))
                    frequency = int(db.fetchall()[0][0]) + contents[word]
                    db.execute("""UPDATE user_progress SET frequency = ? WHERE user_id = ? AND word_id = ?""", (frequency, session["user_id"], word_id))

                db.execute ("SELECT COUNT(*) FROM deck_contents WHERE deck_id = ?", (session["deck_id"],))
                size = db.fetchall()[0][0]
                db.execute("""UPDATE decks SET size = ? WHERE deck_id = ?""", (size, session["deck_id"]))
                con.commit()

            else:
                
                db.execute("""INSERT INTO words (language, word) VALUES (?,?)""", (session["language"], word))
                db.execute("SELECT id FROM words WHERE word = ? AND language = ? ORDER BY id DESC LIMIT 1", (word, session["language"]))
                new_word = db.fetchall()[0][0]
                db.execute("""INSERT INTO user_progress (user_id, word_id, interval, viewings, easy, good, okay, some, none, state, frequency) 
                VALUES (?,?,0,0,0,0,0,0,0, 'new', ?)""",
                (session["user_id"], new_word, contents[word]))
                db.execute ("""INSERT INTO deck_contents (deck_id, word_id, frequency) 
                VALUES (?,?,?)""", 
                (session["deck_id"], new_word, contents[word]))
                con.commit()

        return redirect("/")

    else:
        return render_template("input.html")
        


@app.route("/login", methods=["GET", "POST"])
def login():

    session.clear()

    if request.method == "POST":

        # check that username and password have been entered
        username = request.form.get("username")
        presence (username, "username")
        password = request.form.get("password")
        presence (password, "password")

        # check that these values are correct
        db.execute("SELECT * FROM users WHERE username = ?", (username,))
        rows = db.fetchall()

        if len(rows) != 1 or not check_password_hash(
            rows[0][2], request.form.get("password")
        ):
            return apology("incorrect username and or password", 403)
        
        # create session with the person's id, storing other key settings
        session["user_id"] = rows[0][0]
        session["language"] = rows[0][3]
        session["order"] = rows[0][4]
        session["card"] = ''
        session["creator"] = ''
        session["deck_id"] =''
        session["datetime"] =''
        session["route"] =''
        session['state']=''

        i = 7
        for language in languages:

            session[language] = {"new_seen":int(rows[0][i]), "review_count":0, "reviewed":0}
            i += 1


        return redirect("/")           

    #if method is GET, render the login form
    else:
        return render_template("login.html")


    
@app.route("/logout")
@login_required
def logout():

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")



@app.route("/my_deck")
@login_required
def my_deck():

    #display 50 cards in the deck
    session["route"] = 1
    page = int(request.args.get("page"))
    db.execute ("SELECT size FROM decks WHERE deck_id  = ?", (session["deck_id"],))
    pages = int((int(db.fetchall()[0][0]) - 1)/50)
    db.execute ("SELECT card_order FROM users WHERE id = ?", (session["user_id"],))
    order = db.fetchall()[0][0]
    db.execute (""" SELECT * from words
    JOIN user_progress ON words.id = user_progress.word_id
    JOIN alternates ON alternates.original = words.id
    WHERE id IN (SELECT word_id FROM deck_contents WHERE deck_id = ?) AND user_id = ?
    AND alternates.alternate = user_progress.alternate
    ORDER BY ? LIMIT ?, 50""", (session["deck_id"], session["user_id"], order, 50*page))
    cards = db.fetchall()
    return render_template ("deck.html", cards = cards, page = page, pages=pages)


@app.route("/new_alternate", methods=["GET", "POST"])
@login_required
def new_alternate():

    if request.method == "POST":
    #if card not needed, create a null card
    
        db.execute("""SELECT COUNT(*) FROM alternates WHERE original = ?""", (session["card"],))
        alt_count = db.fetchall()[0][0]

        #get inputted data       
        
        definition = request.form.get("definition")
        presence (definition, "definition")
        frequency = request.form.get("frequency")
        example = request.form.get("example")
        part = request.form.get("part")
        if session["route"] == 0:
            presence (part, "part")
            if session["state"] == "new":
                interval = request.form.get("interval")
                presence (interval, "interval")
            else: 
                db.execute ("""SELECT interval FROM user_progress WHERE user_id = ? AND word_id = ?""", (session["user_id"], session["card"]))
                interval = db.fetchall()[0][0]

        #use inputted data to insert into correct tables
        if interval == "blacklist":
            db.execute("""INSERT INTO alternates (original, alternate, definition, part) VALUES (?,?,'x','x')"""
                        , (session["card"], alt_count))
            db.execute("""UPDATE user_progress SET state = 'blacklisted', alternate = ? WHERE user_id = ? AND word_id = ?"""
                        , (alt_count, session["user_id"], session["card"]))
            con.commit()

            if session["route"] == 0:
                return redirect("/review")
            else:
                return redirect("/my_deck")
            
        else:
            db.execute("""INSERT INTO alternates (definition, frequency, example, part, creator, original, alternate) VALUES (?,?,?,?,?,?,?)""", 
                        (definition, frequency, example, part, session["user_id"], session["card"], alt_count))
            if interval == "known":
                db.execute("""UPDATE user_progress SET state = 'known' WHERE user_id = ? AND word_id = ?""", 
                            (session["user_id"], session["card"]))
                
            else:
                db.execute("""UPDATE user_progress SET interval = ?, due = ?, state = 'learning', alternate = ? WHERE user_id = ? AND word_id = ?""",
                            (interval, int(datetime.now().timestamp()) + int(interval), alt_count, session["user_id"], session["card"]))
                session[session["language"]]["new_seen"] += 1
                session.modified = True
            
            con.commit()
            if session["route"] == 0:
                return redirect("/review")
            else:
                return redirect("/my_deck")

    else:
        #pick the next word that hasn't been dealt with
        db.execute("SELECT word FROM words WHERE id = ?", (session["card"],))
        word = db.fetchall()[0][0]
        db.execute("SELECT state FROM user_progress WHERE user_id = ? AND word_id = ?", (session["user_id"], session["card"]))
        session["state"] = db.fetchall()[0][0]

        if not word:
            return redirect ("/")

        else:
            return render_template ("new_alternate.html", word = word)
        


@app.route("/new_deck", methods = ["GET", "POST"])
@login_required
def new_deck():
    
    if request.method == "POST":
        #get the required variables from the form
        language = request.form.get ("language")
        presence(language, "language")
        if language != session["language"]:
            session["language"] = language
            db.execute("UPDATE users SET language = ? WHERE id = ?", (language, session["user_id"]))
        name = request.form.get("name")
        presence(name, "name")
        medium = request.form.get("medium")
        genre = request.form.get("genre")
        author = request.form.get("author")
        date = request.form.get("date")
        #use the decks table to enter this data
        db.execute("INSERT INTO decks (language, name, medium, genre, author, date, size, creator, public) VALUES (?,?,?,?,?,?,1,?, 'private')"
                   , (language, name, medium, genre, author, date, session["user_id"]))   
        con.commit()
        db.execute("SELECT deck_id FROM decks WHERE name = ?", (name,))
        session["deck_id"] = db.fetchall()[0][0]
        try:
            db.execute("SELECT position FROM users_to_decks WHERE user_id = ? ORDER BY position DESC LIMIT 1", (session["user_id"],))
            position = db.fetchall()[0][0] + 1
        except IndexError:
            position = 0
        db.execute("""INSERT INTO users_to_decks (user_id, deck_id, position) VALUES (?,?,?)""", (session["user_id"], session["deck_id"], position))
        con.commit()
        return redirect ("/input")

    else: 
        return render_template("new_deck.html")
        


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        # check that a username password and confirmation have been entered
        username = request.form.get("username")
        presence (username, "username")
        password = request.form.get("password")
        presence (password, "password")
        confirm = request.form.get("confirm")
        presence (confirm, "confirmation")

        # check that password and username are valid
        if password != confirm:
            return apology("confirmation does not match password", 403)
        db.execute("SELECT COUNT (*) FROM users WHERE username = ?", (username,))
        check_username = db.fetchall()
        if check_username == 1:
            return apology("This username is already taken", 403)
        
        # input new user into database
        hash = generate_password_hash(password)
        db.execute ("INSERT INTO users (username, hash, language, new_cards, finnish_ns, french_ns, german_ns, italian_ns, spanish_ns, time, card_order) VALUES (?, ?, 'Italian', 20, 0, 0, 0, 0, 0, 0, 'words.id')", (username, hash))
        con.commit()
        return redirect ("/")

    else:
        return render_template ("register.html")



@app.route("/reorder", methods=["POST"])
@login_required
def reorder():
    
    deck = request.form.get("deck")
    direction = request.form.get("direction")

    db.execute("""SELECT position FROM users_to_decks WHERE user_id = ? AND deck_id = ?""", (session["user_id"], deck))
    order = db.fetchall()[0][0]

    db.execute("""SELECT COUNT(*) FROM users_to_decks WHERE user_id = ?""", (session["user_id"],))
    total = db.fetchall()[0][0]

    db.execute("""UPDATE users_to_decks SET position = ? WHERE position = ? AND user_id = ?""", (total, order, session["user_id"]))
    con.commit()

    if direction == "first":
        for i in range(order):
            db.execute("""UPDATE users_to_decks SET position = ? WHERE position = ? AND user_id = ?""", (order - i - 1, order - i, session["user_id"]))
            con.commit()
        db.execute("""UPDATE users_to_decks SET position = ? WHERE position = ? AND user_id = ?""", (0, total, session["user_id"]))
        con.commit()

    if direction == "last":
        for i in range(total - order + 1):
            db.execute("""UPDATE users_to_decks SET position = ? WHERE position = ? AND user_id = ?""", (order + i + 1, order + i, session["user_id"]))
            con.commit()
        
    if direction == "+":
        db.execute("""UPDATE users_to_decks SET position = ? WHERE position = ? AND user_id = ?""", (order, order + 1, session["user_id"]))
        con.commit()
        db.execute("""UPDATE users_to_decks SET position = ? WHERE position = ? AND user_id = ?""", (order + 1, total, session["user_id"]))
        con.commit()
    
    else:
        db.execute("""UPDATE users_to_decks SET position = ? WHERE position = ? AND user_id = ?""", (order, order - 1, session["user_id"]))
        con.commit()
        db.execute("""UPDATE users_to_decks SET position = ? WHERE position = ? AND user_id = ?""", (order - 1, total, session["user_id"]))
        con.commit()
    
    return redirect("/")
        


@app.route("/review", methods=["GET", "POST"])
@login_required
def review():

    if request.method =="POST":       

        #reset time
        update()

        #get the value of multiplier
        route = request.form.get("multiplier")

        if route == "known" or route == "blacklisted":
            db.execute("""UPDATE user_progress SET state = ? WHERE user_id = ? AND word_id = ?""", (route, session["user_id"], session["card"]))
            con.commit()
            return redirect ("/review")
        
        multiplier = float(route)

        #get the last interval
        db.execute("""SELECT interval FROM user_progress WHERE user_id = ? AND word_id = ?""", 
                   (session["user_id"], session["card"]))
        interval = db.fetchall()[0][0]

        #if interval is longer than a day, do the maths
        if interval >= 86400:
            if multiplier > 0:
                interval *= multiplier

            else:
                interval = 600

            if multiplier != 0.05:
                due = interval + session["datetime"]
            else:
                due = 900 + session["datetime"]

        #if not, use the preset values for short periods
        else: 
            if multiplier == 0:
                interval = 600
            elif multiplier == 0.05:
                interval = 43200
            elif multiplier == 1:
                interval = 86400
            elif multiplier == 2:
                interval = 345600
            else:
                interval = 846000
            due =  interval + session["datetime"]

        # update the database with this data
        db.execute ("SELECT * FROM user_progress WHERE user_id = ? AND word_id = ?", (session["user_id"], session["card"]))
        viewings = db.fetchall()[0]
        db.execute("""UPDATE user_progress SET due = ?, interval = ?, viewings = ?
        WHERE user_id = ? AND word_id = ?""", (due, interval, viewings[4] + 1, session["user_id"], session["card"]))
        con.commit()

        #update the specific viewing category
        if multiplier == 0:
            db.execute("""UPDATE user_progress SET none = ? WHERE user_id = ? AND word_id = ?"""
            , (viewings[9] + 1, session["user_id"], session["card"]))
        elif multiplier == 0.05:
            db.execute("""UPDATE user_progress SET some = ? WHERE user_id = ? AND word_id = ?"""
            , (viewings[8] + 1, session["user_id"], session["card"]))
        elif multiplier == 1:
            db.execute("""UPDATE user_progress SET okay = ? WHERE user_id = ? AND word_id = ?"""
            , (viewings[7] + 1, session["user_id"], session["card"]))
        elif multiplier == 2:
            db.execute("""UPDATE user_progress SET good = ? WHERE user_id = ? AND word_id = ?"""
            , (viewings[6] + 1, session["user_id"], session["card"]))
        else:
            db.execute("""UPDATE user_progress SET easy = ? WHERE user_id = ? AND word_id = ?"""
            , (viewings[5] + 1, session["user_id"], session["card"]))
            con.commit()
        
        #if already seen, update state and the number of reviews
        if session["state"] == "review":
            if interval < 2500000:
                db.execute ("""UPDATE user_progress SET state = 'learned' WHERE user_id = ? AND word_id = ?"""
                , (session["user_id"], session["card"]))
            else:
                db.execute("""UPDATE user_progress SET state = 'learning' WHERE user_id = ? AND word_id = ?"""
                , (session["user_id"], session["card"]))
            session[session["language"]]["reviewed"] += 1
            session.modified = True
        
        #if the card was new change state to learning, and count a new card seen
        else:
            db.execute("""UPDATE user_progress SET state = 'learning' WHERE user_id = ? AND word_id = ?"""
            , (session["user_id"], session["card"]))
            session[session["language"]]["new_seen"] +=1
            session.modified = True
        
        con.commit()
        return redirect ("/review")

    else:
        update()
        #decide what the next card to show is and display it
        session["route"] = 0
        #if the reviewed percentage is greater than the new percentage, show a new card
        if session[session["language"]]["new_seen"]/session["new_cards"] <= session[session["language"]]["reviewed"]/session[session["language"]]["review_count"] and session[session["language"]]["new_seen"] < session["new_cards"]:
            db.execute (f"""SELECT * FROM user_progress JOIN words ON user_progress.word_id = words.id 
                        JOIN deck_contents ON deck_contents.word_id = user_progress.word_id
                        WHERE user_progress.user_id = ? AND user_progress.state = 'new' AND deck_contents.deck_id = ? AND language = ?
                        ORDER BY {session["order"]} LIMIT 1""", (session["user_id"], session["deck_id"], session["language"]))
            card = db.fetchall()
            session["state"] = "new"

        #if possible, choose the longest overdue card with interval < 1 hr
        else:
            db.execute("""SELECT * FROM user_progress JOIN words ON user_progress.word_id = words.id 
            WHERE user_progress.user_id = ? AND (user_progress.state = 'learning' OR user_progress.state = 'learned') AND words.language = ? 
            AND user_progress.due < ? AND user_progress.interval < 3600
            ORDER BY due LIMIT 1""", (session["user_id"], session["language"], datetime.now().timestamp()))
            card = db.fetchall()

            session["state"] = "review"

            # if there is no short interval card, choose long interval card
            if not card:
                db.execute ("""SELECT * FROM user_progress 
                JOIN words ON user_progress.word_id = words.id 
                WHERE user_progress.user_id = ? AND (user_progress.state = 'learning' OR user_progress.state = 'learned') AND words.language = ? AND user_progress.due < ? 
                ORDER BY due LIMIT 1""", (session["user_id"], session["language"], datetime.now().timestamp()))
                card = db.fetchall()
        
            # if there are any short interval cards to review, do so before ending the session
            if not card:
                db.execute ("""SELECT * FROM user_progress 
                JOIN words ON user_progress.word_id = words.id 
                WHERE user_progress.user_id = ? AND (user_progress.state = 'learning' OR user_progress.state = 'learned') AND words.language = ? 
                AND user_progress.interval < 3600
                ORDER BY due LIMIT 1""", (session["user_id"], session["language"]))
                card = db.fetchall()
        
        # if there are no cards left to review, display session over
        if not card:
            return render_template ("end_review.html", count = session[session["language"]]["reviewed"], new = session[session["language"]]["new_seen"])

        #see if there is already an alternate assigned for this person and word, if so get the data
        session["card"]= card[0][1]
        db.execute("""SELECT * FROM alternates WHERE original = ? AND alternate = 
                (SELECT alternate FROM user_progress WHERE user_id = ? AND word_id = ?)""", (card[0][1], session["user_id"], card[0][1]))
        alternate = db.fetchall()
        #if not assigned find out how many valid alternates there are
        if len(alternate) == 0:
            db.execute ("""SELECT COUNT(*) FROM alternates WHERE original = ? AND NOT creator IN (SELECT creator FROM blacklist WHERE user_id = ?)""",
                         (session["card"], session["user_id"]))
            alt_count = db.fetchall()[0][0]

            # if none then one must be created
            if alt_count == 0:
                return redirect ("/new_alternate")
            
            # if more than one, must be chosen
            if alt_count > 1:
                return redirect ("/choose_alternate")
            
            else:
                db.execute ("""SELECT * FROM alternates WHERE original = ? AND NOT creator IN 
                            (SELECT creator FROM blacklist WHERE user_id = ?)""", (card[0][1], session["user_id"]))
                alternate = db.fetchall()
                db.execute ("""UPDATE user_progress SET alternate = ? WHERE user_id = ? AND word_id = ?""", (alternate[0][1], session["user_id"], session["card"]))
                con.commit()

        session["card"]= card[0][1]
        db.execute("""SELECT * FROM alternates WHERE original = ? AND alternate = 
                (SELECT alternate FROM user_progress WHERE user_id = ? AND word_id = ?)""", (card[0][1], session["user_id"], card[0][1]))
        alternate = db.fetchall()
        return render_template ("review.html", card = card, alternate = alternate)
        
            

@app.route ("/search_decks", methods=["GET", "POST"])
@login_required
def search_decks ():
    
    if request.method == "POST":

        id = request.form.get ("id")
        name = request.form.get("name")
        medium = request.form.get("medium")
        genre = request.form.get("genre")
        author = request.form.get("author")
        date = request.form.get("date")
    
        db.execute("""SELECT * FROM decks WHERE deck_id LIKE ? OR language LIKE ? OR name LIKE ? OR medium LIKE ? OR genre LIKE ? OR author LIKE ? OR date LIKE ?"""
        , (id, session["language"], name, medium, genre, author, date))
        matching = db.fetchall()
        return render_template ("found.html", matching = matching)

    else:
        return render_template ("search_decks.html")



@app.route("/settings", methods = ["GET", "POST"])
@login_required
def settings ():
    
    if request.method == "POST":
        
        #update card order
        card_order = request.form.get ("card_order")
        if card_order:
            session["order"] = card_order
            db.execute ("UPDATE users SET card_order = ? WHERE id = ?", (card_order, session["user_id"]))
            
        #update number of new cards
        try:
            new_cards = int(request.form.get ("new_cards"))
            session["new_cards"] = new_cards
            db.execute ("UPDATE users SET new_cards = ? WHERE id = ?", (new_cards, session["user_id"]))
        except ValueError:
            a = 1
            del a

        con.commit()
        return redirect("/")
       
    else:
        return render_template ("settings.html")



@app.route("/view_blacklist", methods=["GET", "POST"])
@login_required
def view_blacklist():

    if request.method == "POST":
        
        creator = request.form.get("creator")
        db.execute("""DELETE FROM blacklist WHERE user_id = ? AND creator = ?""", (session["user_id"], creator))
        con.commit()
        return redirect("/view_blacklist")
    
    else:  

        db.execute ("""SELECT id, username FROM users WHERE id IN (SELECT creator FROM blacklist WHERE user_id = ?)""", (session["user_id"],)) 
        blacklist = db.fetchall()
        return render_template ("blacklist.html", blacklist = blacklist)

@app.route("/view_deck", methods=["POST"])
@login_required
def view_deck():
    session["deck_id"] = request.form.get("deck")
    return redirect ("/my_deck?page=0")
