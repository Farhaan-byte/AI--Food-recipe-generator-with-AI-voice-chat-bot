import os
import json
import requests
from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify
from flask_cors import CORS
from supabase import create_client, Client

# Initialize Flask app
app = Flask(__name__, static_url_path='/static')
app.secret_key = os.urandom(24)
CORS(app)

# Initialize Supabase
SUPABASE_URL = "https://hazgghhpurqmxaywejxi.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhhemdnaGhwdXJxbXhheXdlanhpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDM4NzYyNzIsImV4cCI6MjA1OTQ1MjI3Mn0.66YnxFAv1udH-E4ov4uphWxH2-d3Wzsf1wHg9WDd8uk"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Load recipes
with open("data/recipes.json", "r", encoding="utf-8") as f:
    RECIPES = json.load(f)

# ------------------ ROUTES ------------------

@app.route("/")
def home():
    if 'user_id' not in session:
        return redirect(url_for("login"))
    return redirect(url_for("generate_form"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        try:
            response = supabase.auth.sign_up({
                "email": email,
                "password": password
            })

            if hasattr(response, "error") and response.error:
                return render_template("signup.html", error_message=response.error.message)

            if not hasattr(response, "user") or response.user is None:
                return render_template("signup.html", error_message="Signup failed. No user returned.")

            user = response.user
            user_id = user.id

            supabase.table("users").upsert({
                "user_id": user_id,
                "name": name,
                "email": email
            }).on_conflict("email").execute()

            session["user_id"] = user_id
            session["email"] = email
            session["name"] = name

            return redirect(url_for("profile"))

        except Exception as e:
            return render_template("signup.html", error_message=f"Signup error: {str(e)}")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        try:
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if hasattr(response, 'error') and response.error:
                return render_template("login.html", error_message=response.error.message)

            if not response.user:
                return render_template("login.html", error_message="Login failed. No user returned.")

            user = response.user
            user_id = user.id

            session["user_id"] = user_id
            session["email"] = email

            profile_resp = supabase.table("users").select("*").eq("user_id", user_id).execute()
            profile = profile_resp.data[0] if profile_resp.data else {}

            if profile.get("food_preference") and profile.get("dietary_goal"):
                return redirect(url_for("generate_form"))
            else:
                return redirect(url_for("profile"))

        except Exception as e:
            return render_template("login.html", error_message=f"Login error: {str(e)}")

    return render_template("login.html")


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    email = session["email"]

    if request.method == "POST":
        data = {
            "user_id": user_id,
            "email": email,
            "food_preference": request.form.get("food_preference"),
            "dietary_goal": request.form.get("dietary_goal"),
            "allergies": request.form.getlist("allergies"),
            "flavor_profile": request.form.getlist("flavors")
        }

        try:
            supabase.table("users").upsert(data).execute()
            return redirect(url_for("generate_form"))
        except Exception as e:
            return f"<h3>Error saving profile: {e}</h3>"

    user_response = supabase.table("users").select("*").eq("user_id", user_id).execute()
    profile = user_response.data[0] if user_response.data else {}

    return render_template("profile.html", profile=profile)


@app.route("/generate", methods=["GET"])
def generate_form():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template("generate.html")


@app.route("/generate_recipe", methods=["POST"])
def generate_recipe():
    print("== FORM DEBUG ==")
    print("Form data:", request.form)
    print("Ingredients:", request.form.getlist("ingredients[]"))
    print("Tools:", request.form.getlist("tools"))
    print("Time:", request.form.get("time"))
    print("Skill:", request.form.get("skill"))
    print("Chef Mode:", request.form.get("chef_mode"))
    print("=================")

    if 'user_id' not in session:
        return redirect(url_for('login'))

    ingredients = [i.strip().lower() for i in request.form.getlist("ingredients[]") if i.strip()]
    if not ingredients:
        return "<h3>Error: Please provide at least one ingredient.</h3>"

    tools = request.form.getlist("tools")
    time = int(request.form.get("time", 0))
    skill = request.form.get("skill", "Beginner")

    response = supabase.table("users").select("*").eq("user_id", session['user_id']).execute()
    if not response.data:
        return "No user profile found."

    user = response.data[0]
    user_profile = {
        "food_preference": user.get("food_preference", ""),
        "dietary_goal": user.get("dietary_goal", ""),
        "allergies": user.get("allergies", []),
        "flavor_profile": user.get("flavor_profile", []),
        "ingredients": ingredients,
        "tools": tools,
        "time": time,
        "skill": skill,
        "chef_mode": request.form.get("chef_mode", "Quick & Easy")
    }

    try:
        from recommend import recommend_recipes
        recipes = recommend_recipes(user_profile)
        return render_template("recipes.html", recipes=recipes)
    except Exception as e:

        flash(f"Error generating recipes: {e}", "danger")
        return redirect(url_for("generate_form"))

@app.route('/recipe_detail/<int:recipe_id>')
def recipe_detail(recipe_id):
    recipe = next((r for r in RECIPES if r["id"] == recipe_id), None)
    if not recipe:
        return render_template("404.html"), 404
    return render_template("recipe_detail.html", recipe=recipe)


@app.route("/save_favorite", methods=["POST"])
def save_favorite():
    try:
        data = {
            "recipe_id": request.form.get("recipe_id"),
            "title": request.form.get("title"),
            "image": request.form.get("image"),
            "user_id": session['user_id']
        }
        supabase.table("favorites").insert(data).execute()
        flash("Recipe saved to favorites!", "success")
        return redirect(url_for("favorites"))
    except Exception as e:
        flash(f"Error saving favorite: {e}", "danger")
        return redirect(url_for("generate_form"))


@app.route("/favorites")
def favorites():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        response = supabase.table("favorites").select("*").eq("user_id", session['user_id']).execute()
        recipes = response.data
        return render_template("favorites.html", recipes=recipes)
    except Exception as e:
        flash(f"Error fetching favorites: {e}", "danger")
        return redirect(url_for("generate_form"))


@app.route("/remove_favorite/<int:id>", methods=["POST"])
def remove_favorite(id):
    try:
        supabase.table("favorites").delete().eq("id", id).execute()
        flash("Favorite removed successfully!", "success")
        return redirect(url_for("favorites"))
    except Exception as e:
        flash(f"Error removing favorite: {e}", "danger")
        return redirect(url_for("favorites"))
import requests  # make sure this import is near the top of app.py if not already

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        question = data.get("question", "").strip()
        recipe = data.get("recipe", {})

        if not question or not recipe:
            return jsonify({"response": "Missing question or recipe."}), 400

        prompt = f"""
        You are a helpful recipe assistant. Answer the user's question based on the following recipe.

        Title: {recipe.get('title')}
        Ingredients: {', '.join(recipe.get('ingredients', []))}
        Instructions: {' '.join(recipe.get('instructions', []))}
        Flavors: {', '.join(recipe.get('flavors', []))}
        Allergens: {', '.join(recipe.get('allergens', []))}

        Question: {question}

        Answer:
        """

        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",  # Or whatever model you are using
                "prompt": prompt,
                "stream": False
            }
        )

        result = response.json()
        reply = result.get("response", "Sorry, I couldn't generate a response.")

        return jsonify({"response": reply.strip()})

    except Exception as e:
        print("Ollama chat error:", e)
        return jsonify({"response": "Error processing your request."}), 500


if __name__ == "__main__":
    app.run(debug=True)
