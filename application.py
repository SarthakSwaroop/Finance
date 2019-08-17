
import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import requests
import urllib.parse

from helpers import apology, login_required, lookup, usd


# Configure application
app = Flask(__name__)
app.secret_key = "some secret key"

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")



#++++++++++++++++++++++++++++++++++++++++++ INDEX ++++++++++++++++++++++++++++++++++++++++++

@app.route("/")
@login_required
def index():

    rows, funds, wallet = getWallet()

    return render_template("index.html", history=rows, funds=funds, wallet=wallet+funds)


#++++++++++++++++++++++++++++++++++++++++++ BUY ++++++++++++++++++++++++++++++++++++++++++

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    jStockPrice = {}

    if request.method == "GET":
        rows, funds, wallet = getWallet()

        return render_template("buy.html", history=rows, funds=funds)

    if request.method == "POST" and request.form.get("type") == "quote":
        if(not request.form.get("stock")):
            return apology("Not a valid stock")

        fPrice = quotePrice(request.form.get("stock"))

        return jsonify({"price":fPrice})

    else:
        user_id = session["user_id"]
        stockAsked = request.form.get("symbol").lower()
        stockPrice = float(quotePrice(stockAsked))

        if not user_id or not stockAsked or not request.form.get("shares") or not stockPrice or stockPrice < 0:
            return apology("Sorry, Check your input again!")

        stockQty = float(request.form.get("shares"))

        rows = db.execute("SELECT avg(u.cash)+ coalesce(sum(p.transactionPriceUSD*quantity),0) as fundsAvailable FROM users u left join transactionHistory p on p.userID = u.id where u.id = :p_userID", p_userID=user_id)
        funds = rows[0]["fundsAvailable"]

        if funds - (stockQty*stockPrice) > 0:
            db.execute("INSERT INTO transactionHistory (userID, stockSymbol, quantity, transactionPriceUSD, transactionType) values(:p_userID, :p_symbol, :p_quantity, :p_price, -1)", p_userID=user_id, p_symbol=stockAsked , p_quantity=stockQty, p_price=-stockPrice)

            message = (f"Thank you for your purchase!")
            flash(message)
            return redirect("/")
        else:
            return apology("Not enough funds")


#++++++++++++++++++++++++++++++++++++++++++ CHECK ++++++++++++++++++++++++++++++++++++++++++

@app.route("/check", methods=["GET", "POST"])
def check():

    if request.method == "POST":
        rows = db.execute("SELECT COUNT(id) as count FROM users where username = :name", name=request.form.get("name"))
        available = ""
        if rows[0]["count"] > 0:
            available = "not available"

        else:
            available = "available"

        return jsonify({"available":available})

    userName = request.args.get("username")
    rows = db.execute("SELECT COUNT(id) as count FROM users where username = :name", name=userName)

    if not userName or rows[0]["count"] > 0:
        return jsonify(False)

    else:
        return jsonify(True), 200

#++++++++++++++++++++++++++++++++++++++++++ HISTORY ++++++++++++++++++++++++++++++++++++++++++

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    rows, funds = getHistory()

    if not rows:
        print("NO ROWS FOUND<<<<<<<<<<<<<<<<")
        return redirect("/buy")
    else:
        return render_template("history.html", history=rows, funds=funds)




#++++++++++++++++++++++++++++++++++++++++++ LOGIN ++++++++++++++++++++++++++++++++++++++++++

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    # session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        session.clear()

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


#++++++++++++++++++++++++++++++++++++++++++ LOGOUT ++++++++++++++++++++++++++++++++++++++++++

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    flash("Hope to see you again, soon! :-) ")
    return redirect("/")


#++++++++++++++++++++++++++++++++++++++++++ QUOTE ++++++++++++++++++++++++++++++++++++++++++

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("Please enter the stock.")

        stock = lookup(request.form.get("symbol"))

        if not stock:
            return apology("There is no such stock.")

        stock["price"] = usd(stock["price"])

        return render_template("quoted.html", stock=stock)

    else:
        return render_template("quote.html")


#++++++++++++++++++++++++++++++++++++++++++ REGISTER ++++++++++++++++++++++++++++++++++++++++++

@app.route("/register", methods=["GET", "POST"])
def register():
    sRegMessage = ""

    if request.method == "GET":
        return render_template("register.html")

    else:
        if(not request.form.get("username")
            or not request.form.get("password")
            or not request.form.get("confirmation")
            or request.form.get("password") != request.form.get("confirmation")):

            return apology("Oooops")

        username = request.form.get("username")
        pw = request.form.get("password")
        pw_hash = generate_password_hash(pw)


        rows = db.execute("SELECT count(id) as count from users where username = :name", name=username)

        if rows[0]["count"] > 0:
           return apology("username already exists")

        db.execute("INSERT INTO users (username, hash) VALUES(:name, :pw)", name=username, pw=pw_hash)

        flash("Thank you for registering! You can now login!")
        return render_template("register.html")


#++++++++++++++++++++++++++++++++++++++++++ SELL ++++++++++++++++++++++++++++++++++++++++++

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    user_id = session["user_id"]


    if request.method == "GET":
        rows, funds = getWallet()

        stocks = db.execute("SELECT stockSymbol, sum(quantity*-transactionType) as qty FROM transactionHistory WHERE userID = :p_uID GROUP BY stockSymbol", p_uID = session["user_id"])

        stocks_clean = [stock["stockSymbol"] for stock in stocks if stock["qty"] > 0]
        print(stocks_clean)

        return render_template("sell.html", history=rows, funds=funds, select=stocks_clean)


    if request.method == "POST" and request.form.get("type") == "sale":

        fPrice = quotePrice(request.form.get("stock").lower())
        stockAsked = request.form.get("stock").lower()
        stockQty = 0

        rows = db.execute("SELECT SUM(quantity) as quantity, avg(CASE WHEN transactionPriceUSD < 0 THEN transactionPriceUSD else NULL END)*-1 as avgPurchasePrice FROM transactionHistory WHERE userID = :p_uid AND stockSymbol = :p_stock", p_uid=user_id, p_stock=stockAsked)

        availableQty = rows[0]["quantity"]
        avgBuyPrice = rows[0]["avgPurchasePrice"]

        return jsonify({"price":fPrice, "quantity":availableQty, "buyPrice":avgBuyPrice})


    else:
        stockSold = request.form.get("sell-select")
        sellQty = float(request.form.get("shares"))
        sellPrice = quotePrice(stockSold)

        if not stockSold or not sellQty or not sellPrice:
            return apology("Missing Values - try again")

        rows = db.execute("SELECT SUM(quantity) as quantity, avg(CASE WHEN transactionPriceUSD < 0 THEN transactionPriceUSD else NULL END)*-1 as avgPurchasePrice FROM transactionHistory WHERE userID = :p_uid AND stockSymbol = :p_stock", p_uid=user_id, p_stock=stockSold)

        availableQty = rows[0]["quantity"]
        avgBuyPrice = rows[0]["avgPurchasePrice"]

        if sellQty > availableQty or sellQty <= 0:
            return apology("Missing Values - try again")

        print(">>>>>>>>>>> WORKED!!",stockSold, sellQty, sellPrice, availableQty, avgBuyPrice)

        db.execute("INSERT INTO transactionHistory (userID, stockSymbol, quantity, transactionPriceUSD, transactionType) values(:p_uid, :p_stock, :p_qty, :p_price, 1)", p_uid=user_id, p_stock=stockSold, p_qty=sellQty, p_price=sellPrice)


        flash("Thank you for your sale! See your updated wallet below")
        return redirect("/sell")







#++++++++++++++++++++++++++++++++++++++++++ ERROR  ++++++++++++++++++++++++++++++++++++++++++
def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)


@app.route("/getRecomm", methods=["GET", "POST"])
@login_required
def updateAllStocks():


    return redirect("/login")

def getHistory():
    rows = db.execute("SELECT transactionDate, CASE WHEN transactionType = 1 THEN 'sale' WHEN transactionType = -1 THEN 'purchase' ELSE NULL END AS salesType, stockSymbol, quantity, transactionPriceUSD, round(quantity*transactionPriceUSD,2) as totalTransactionUSD FROM transactionHistory where userID = :uID ORDER BY transactionDate DESC;", uID=session["user_id"])
    rFunds = db.execute("SELECT avg(u.cash)+ coalesce(sum(p.transactionPriceUSD*quantity),0) as fundsAvailable FROM users u left join transactionHistory p on p.userID = u.id where u.id = :p_userID;", p_userID=session["user_id"])
    funds = usd(rFunds[0]["fundsAvailable"])
def getWallet():
    rows = db.execute("SELECT stockSymbol, round(sum(quantity*-transactionType),2) as TotalStockHeld, NULL as latestPrice, NULL as TotalValueUSD FROM transactionHistory where userID = :uID GROUP BY stockSymbol", uID=session["user_id"])
    rFunds = db.execute("SELECT avg(u.cash)+ coalesce(sum(p.transactionPriceUSD*quantity),0) as fundsAvailable FROM users u left join transactionHistory p on p.userID = u.id where u.id = :p_userID;", p_userID=session["user_id"])
    funds = rFunds[0]["fundsAvailable"]

    totalWallet = 0

    for row in rows:
        latestPrice = quotePrice(row["stockSymbol"])
        row["latestPrice"] = usd(latestPrice)
        row["TotalValueUSD"] = latestPrice*row["TotalStockHeld"]
        totalWallet += row["TotalValueUSD"]
        row["TotalValueUSD"] = usd(row["TotalValueUSD"])
        row["stockSymbol"] = row["stockSymbol"].upper()

    rows_clean = [row for row in rows if row["TotalStockHeld"]>0]

    appendString = {}

    appendString["stockSymbol"] = "CASH"
    appendString["TotalStockHeld"] = ""
    appendString["latestPrice"] = ""
    appendString["TotalValueUSD"] = usd(funds)
    rows_clean.append(appendString)

    return rows_clean, funds, totalWallet
    return rows, funds





def quotePrice(stock):

    fPrice = 0

    if stock == "":
        fPrice = -1
    else:

        jStockPrice = lookup(stock)

    if jStockPrice:
        fPrice = jStockPrice["price"]
    else:
        print("no price found")
        fPrice = -1

    return fPrice