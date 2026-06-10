"""
BrowserMind — Complex Task Set
================================
مهام تدريب متقدمة تغطي:
  - إنشاء حسابات (multi-step signup flows)
  - تسجيل الدخول والخروج (login / logout)
  - ملء forms معقدة (dropdowns, checkboxes, radio buttons, date pickers)
  - تسجيل بيانات كاملة (name, email, phone, address, country)
  - إدارة الحساب (profile edit, password change, preferences)
  - مهام multi-step (wizard forms, checkout flows)
  - مواقع demo/sandbox آمنة للتدريب

كل entry: (goal, start_url, task_type, difficulty)
  task_type: "signup" | "login" | "logout" | "form_fill" | "dropdown" |
             "checkbox" | "multistep" | "account" | "search_filter"
  difficulty: 1 (easy) → 3 (hard)
"""

from typing import List, Tuple

# ─────────────────────────────────────────────────────────────────────────────
#  Type alias
# ─────────────────────────────────────────────────────────────────────────────
Task = Tuple[str, str, str, int]   # (goal, url, task_type, difficulty)


# ─────────────────────────────────────────────────────────────────────────────
#  1. مواقع Demo & Sandbox — آمنة 100% للتدريب
# ─────────────────────────────────────────────────────────────────────────────

DEMO_FORM_TASKS: List[Task] = [
    # ── httpbin.org ────────────────────────────────────────────────────────
    ("fill the name field with John Smith in the contact form",
     "https://httpbin.org/forms/post", "form_fill", 1),

    ("fill the customer email field with test@example.com",
     "https://httpbin.org/forms/post", "form_fill", 1),

    ("select the size large from the pizza size dropdown",
     "https://httpbin.org/forms/post", "dropdown", 2),

    ("check the bacon topping checkbox",
     "https://httpbin.org/forms/post", "checkbox", 1),

    ("check all available topping checkboxes in the form",
     "https://httpbin.org/forms/post", "checkbox", 2),

    ("fill the delivery time field and submit the pizza order form",
     "https://httpbin.org/forms/post", "multistep", 2),

    ("fill all fields in the pizza order form: name John, email john@test.com, size large, submit",
     "https://httpbin.org/forms/post", "multistep", 3),

    # ── W3Schools demo forms ────────────────────────────────────────────────
    ("fill the first name field with Alice in the HTML form",
     "https://www.w3schools.com/html/html_forms.asp", "form_fill", 1),

    ("fill the last name field with Johnson",
     "https://www.w3schools.com/html/html_forms.asp", "form_fill", 1),

    ("submit the HTML form after filling first name Bob and last name Smith",
     "https://www.w3schools.com/html/html_forms.asp", "multistep", 2),

    ("select female from the gender dropdown",
     "https://www.w3schools.com/html/tryit.asp?filename=tryhtml_elem_select",
     "dropdown", 1),

    ("select Saab from the car brand dropdown menu",
     "https://www.w3schools.com/html/tryit.asp?filename=tryhtml_elem_select",
     "dropdown", 1),

    ("choose the radio button for male gender",
     "https://www.w3schools.com/html/html_forms.asp", "checkbox", 1),

    # ── Playwright demo app ─────────────────────────────────────────────────
    ("fill the username and password fields then click login",
     "https://the-internet.herokuapp.com/login", "login", 1),

    ("login with username tomsmith and password SuperSecretPassword!",
     "https://the-internet.herokuapp.com/login", "login", 2),

    ("check all checkboxes on the checkboxes page",
     "https://the-internet.herokuapp.com/checkboxes", "checkbox", 1),

    ("uncheck the first checkbox on the page",
     "https://the-internet.herokuapp.com/checkboxes", "checkbox", 1),

    ("select an option from the dropdown list",
     "https://the-internet.herokuapp.com/dropdown", "dropdown", 1),

    ("select option 2 from the dropdown",
     "https://the-internet.herokuapp.com/dropdown", "dropdown", 1),

    ("select option 1 from the dropdown",
     "https://the-internet.herokuapp.com/dropdown", "dropdown", 2),

    ("fill the name field and message field in the form and submit",
     "https://the-internet.herokuapp.com/forgot_password", "form_fill", 2),

    ("enter the email address test@example.com to reset password",
     "https://the-internet.herokuapp.com/forgot_password", "form_fill", 1),

    ("hover over each item in the navigation menu",
     "https://the-internet.herokuapp.com/hovers", "form_fill", 2),

    # ── DemoQA forms ────────────────────────────────────────────────────────
    ("fill the first name with Ahmed in the practice form",
     "https://demoqa.com/automation-practice-form", "form_fill", 1),

    ("fill the last name with Hassan",
     "https://demoqa.com/automation-practice-form", "form_fill", 1),

    ("fill email field with ahmed.hassan@test.com",
     "https://demoqa.com/automation-practice-form", "form_fill", 1),

    ("select male as the gender option",
     "https://demoqa.com/automation-practice-form", "checkbox", 1),

    ("select female as the gender option",
     "https://demoqa.com/automation-practice-form", "checkbox", 1),

    ("fill the mobile number field with 01012345678",
     "https://demoqa.com/automation-practice-form", "form_fill", 1),

    ("select Sports and Reading as hobbies",
     "https://demoqa.com/automation-practice-form", "checkbox", 2),

    ("fill the current address field with 123 Main Street Cairo Egypt",
     "https://demoqa.com/automation-practice-form", "form_fill", 2),

    ("complete the full student registration form with name Ahmed Hassan, email ahmed@test.com, mobile 01012345678, gender male",
     "https://demoqa.com/automation-practice-form", "multistep", 3),

    ("fill the text box with full name Sara Ali and email sara@test.com",
     "https://demoqa.com/text-box", "form_fill", 1),

    ("fill the current address as 456 Nile Street and permanent address as same",
     "https://demoqa.com/text-box", "form_fill", 2),

    ("click the submit button after filling the text box form",
     "https://demoqa.com/text-box", "form_fill", 1),

    ("select the checkbox for Home",
     "https://demoqa.com/checkbox", "checkbox", 1),

    ("expand the tree and select Desktop checkbox",
     "https://demoqa.com/checkbox", "checkbox", 2),

    ("expand Home and select Documents folder",
     "https://demoqa.com/checkbox", "checkbox", 2),

    ("select the Yes radio button",
     "https://demoqa.com/radio-button", "checkbox", 1),

    ("select the Impressive radio button",
     "https://demoqa.com/radio-button", "checkbox", 1),

    ("add a row to the table with first name John and last name Doe",
     "https://demoqa.com/webtables", "form_fill", 2),

    ("delete the first row from the web table",
     "https://demoqa.com/webtables", "form_fill", 2),

    ("search for Cierra in the web tables search box",
     "https://demoqa.com/webtables", "form_fill", 1),

    ("fill the login form with username admin and password admin123",
     "https://demoqa.com/login", "login", 1),

    ("select a date from the date picker",
     "https://demoqa.com/date-picker", "form_fill", 2),

    ("select January 15 2024 from the date picker",
     "https://demoqa.com/date-picker", "form_fill", 3),

    ("move the slider to position 75",
     "https://demoqa.com/slider", "form_fill", 2),

    ("fill the from and to fields in the select menu",
     "https://demoqa.com/select-menu", "dropdown", 2),

    ("select Red from the color dropdown",
     "https://demoqa.com/select-menu", "dropdown", 1),

    ("select a value from the old style select menu",
     "https://demoqa.com/select-menu", "dropdown", 1),

    ("select multiple colors from the multiselect dropdown",
     "https://demoqa.com/select-menu", "dropdown", 2),

    # ── Juice Shop (OWASP demo store) ─────────────────────────────────────
    ("register a new account with email newuser@test.com and password Test123!",
     "https://juice-shop.herokuapp.com/#/register", "signup", 2),

    ("fill the registration form: email test@juice.com, password SecurePass1!, security question with answer",
     "https://juice-shop.herokuapp.com/#/register", "signup", 3),

    ("login to juice shop with email admin@juice-sh.op and password admin123",
     "https://juice-shop.herokuapp.com/#/login", "login", 2),

    ("search for apple juice in the search box",
     "https://juice-shop.herokuapp.com", "form_fill", 1),

    ("add apple juice to the shopping basket",
     "https://juice-shop.herokuapp.com", "form_fill", 2),

    ("select a security question from the dropdown during registration",
     "https://juice-shop.herokuapp.com/#/register", "dropdown", 2),
]


# ─────────────────────────────────────────────────────────────────────────────
#  2. GitHub — إنشاء حساب وإدارة
# ─────────────────────────────────────────────────────────────────────────────

GITHUB_TASKS: List[Task] = [
    # Login
    ("login to GitHub with username testuser and password testpass123",
     "https://github.com/login", "login", 1),

    ("enter username in the GitHub login form",
     "https://github.com/login", "form_fill", 1),

    ("enter password in the GitHub login form",
     "https://github.com/login", "form_fill", 1),

    ("click the sign in button on GitHub login page",
     "https://github.com/login", "login", 1),

    # Signup
    ("start creating a new GitHub account by entering email address newdev@example.com",
     "https://github.com/signup", "signup", 1),

    ("fill the GitHub signup form with email newdev@test.com",
     "https://github.com/signup", "signup", 2),

    ("navigate to GitHub signup page and fill the email field",
     "https://github.com", "signup", 1),

    # Navigation after login (assumes logged in state via seed)
    ("navigate to GitHub settings page",
     "https://github.com/settings", "account", 1),

    ("click on profile and then settings in GitHub",
     "https://github.com", "account", 2),

    # Search with filters
    ("search for python machine learning repositories and filter by most stars",
     "https://github.com/search", "search_filter", 2),

    ("filter GitHub search results by Python language",
     "https://github.com/search?q=machine+learning", "search_filter", 2),

    ("filter repositories by updated recently",
     "https://github.com/search?q=neural+network&type=repositories",
     "search_filter", 2),

    # Forms on GitHub
    ("create a new repository by filling the repository name field",
     "https://github.com/new", "form_fill", 2),

    ("fill the repository description field",
     "https://github.com/new", "form_fill", 1),

    ("select private visibility for the new repository",
     "https://github.com/new", "checkbox", 1),

    ("check the add README checkbox when creating a repository",
     "https://github.com/new", "checkbox", 1),

    ("select a license from the license dropdown for new repository",
     "https://github.com/new", "dropdown", 2),

    ("select MIT License from the license chooser",
     "https://github.com/new", "dropdown", 2),

    ("select Python from the gitignore template dropdown",
     "https://github.com/new", "dropdown", 2),

    # Issues
    ("open a new issue with title Bug report: login fails on mobile",
     "https://github.com/torvalds/linux/issues/new", "form_fill", 2),

    ("fill the issue description field with steps to reproduce the bug",
     "https://github.com/torvalds/linux/issues/new", "form_fill", 2),
]


# ─────────────────────────────────────────────────────────────────────────────
#  3. Reddit — تسجيل دخول وخروج، نشر
# ─────────────────────────────────────────────────────────────────────────────

# REDDIT_TASKS: List[Task] = [
#     # Login
#     ("log in to Reddit with username and password",
#      "https://www.reddit.com/login", "login", 1),
# 
#     ("enter username in the Reddit login form",
#      "https://www.reddit.com/login", "form_fill", 1),
# 
#     ("enter password in the Reddit login field",
#      "https://www.reddit.com/login", "form_fill", 1),
# 
#     ("click the login button on Reddit",
#      "https://www.reddit.com/login", "login", 1),
# 
#     # Signup
#     ("start Reddit registration by clicking sign up",
#      "https://www.reddit.com", "signup", 1),
# 
#     ("fill the email field on Reddit signup page",
#      "https://www.reddit.com/register", "signup", 1),
# 
#     ("fill the username field with a new username during Reddit signup",
#      "https://www.reddit.com/register", "signup", 2),
# 
#     ("fill the password field during Reddit account creation",
#      "https://www.reddit.com/register", "signup", 2),
# 
#     # Navigation
#     ("click on a subreddit link to navigate to it",
#      "https://www.reddit.com", "form_fill", 1),
# 
#     ("search for python subreddit using the search box",
#      "https://www.reddit.com", "form_fill", 1),
# 
#     # Post creation
#     ("click create post button in a subreddit",
#      "https://www.reddit.com/r/python/submit", "form_fill", 1),
# 
#     ("fill the post title field",
#      "https://www.reddit.com/r/python/submit", "form_fill", 1),
# 
#     ("type the post body text",
#      "https://www.reddit.com/r/python/submit", "form_fill", 2),
# 
#     ("select the post type as link",
#      "https://www.reddit.com/r/python/submit", "dropdown", 2),
# ]
REDDIT_TASKS = []   # Temporarily disabled for DAgger stability



# ─────────────────────────────────────────────────────────────────────────────
#  4. Stack Overflow — إنشاء حساب، طرح أسئلة
# ─────────────────────────────────────────────────────────────────────────────

STACKOVERFLOW_TASKS: List[Task] = [
    # Login
    ("log in to Stack Overflow with email and password",
     "https://stackoverflow.com/users/login", "login", 1),

    ("enter email address in Stack Overflow login",
     "https://stackoverflow.com/users/login", "form_fill", 1),

    ("enter password in Stack Overflow login form",
     "https://stackoverflow.com/users/login", "form_fill", 1),

    # Signup
    ("create a new Stack Overflow account",
     "https://stackoverflow.com/users/signup", "signup", 2),

    ("fill the display name field during Stack Overflow signup",
     "https://stackoverflow.com/users/signup", "signup", 1),

    ("fill the email field during Stack Overflow registration",
     "https://stackoverflow.com/users/signup", "signup", 1),

    ("fill the password field during Stack Overflow signup",
     "https://stackoverflow.com/users/signup", "signup", 1),

    # Ask question
    ("click the ask question button",
     "https://stackoverflow.com", "form_fill", 1),

    ("fill the question title with How to center a div in CSS",
     "https://stackoverflow.com/questions/ask", "form_fill", 1),

    ("fill the question body field with details about the problem",
     "https://stackoverflow.com/questions/ask", "form_fill", 2),

    ("add tags python and pandas to the question",
     "https://stackoverflow.com/questions/ask", "form_fill", 2),

    # Search & filter
    ("search for questions about python asyncio",
     "https://stackoverflow.com", "form_fill", 1),

    ("filter questions by newest first",
     "https://stackoverflow.com/questions", "search_filter", 1),

    ("filter by unanswered questions",
     "https://stackoverflow.com/questions", "search_filter", 2),
]


# ─────────────────────────────────────────────────────────────────────────────
#  5. مهام Multi-step معقدة — Checkout Flows & Wizards
# ─────────────────────────────────────────────────────────────────────────────

MULTISTEP_TASKS: List[Task] = [
    # ── OpenCart demo (إن كان متاح) ────────────────────────────────────────
    ("register a new account: fill firstname, lastname, email, phone, and password",
     "https://opencart.abstracta.us/index.php?route=account/register", "signup", 3),

    ("fill the first name field with Mohamed",
     "https://opencart.abstracta.us/index.php?route=account/register", "form_fill", 1),

    ("fill the last name field with Ali",
     "https://opencart.abstracta.us/index.php?route=account/register", "form_fill", 1),

    ("fill the email with mohamedali@test.com",
     "https://opencart.abstracta.us/index.php?route=account/register", "form_fill", 1),

    ("fill the phone number with 01098765432",
     "https://opencart.abstracta.us/index.php?route=account/register", "form_fill", 1),

    ("fill the password and confirm password fields",
     "https://opencart.abstracta.us/index.php?route=account/register", "form_fill", 2),

    ("agree to the privacy policy checkbox and submit the registration form",
     "https://opencart.abstracta.us/index.php?route=account/register", "checkbox", 2),

    ("login to the store with email user@test.com and password Test1234!",
     "https://opencart.abstracta.us/index.php?route=account/login", "login", 2),

    # ── Checkout wizard steps ────────────────────────────────────────────────
    ("fill the billing address: street 123 Tahrir Square, city Cairo, select country Egypt",
     "https://opencart.abstracta.us/index.php?route=checkout/checkout", "multistep", 3),

    ("select Egypt from the country dropdown in the billing form",
     "https://opencart.abstracta.us/index.php?route=checkout/checkout", "dropdown", 2),

    ("select Cairo Governorate from the region dropdown",
     "https://opencart.abstracta.us/index.php?route=checkout/checkout", "dropdown", 2),

    ("select the flat shipping rate option",
     "https://opencart.abstracta.us/index.php?route=checkout/checkout", "checkbox", 2),

    ("select cash on delivery as the payment method",
     "https://opencart.abstracta.us/index.php?route=checkout/checkout", "checkbox", 2),

    # ── W3Schools multi-field ────────────────────────────────────────────────
    ("fill all fields: first name, last name, and submit the form",
     "https://www.w3schools.com/html/tryit.asp?filename=tryhtml_form_submit",
     "multistep", 2),

    ("fill a form with name Mohammed and email mohammed@test.com and submit",
     "https://www.w3schools.com/html/tryit.asp?filename=tryhtml_form_submit",
     "multistep", 2),
]


# ─────────────────────────────────────────────────────────────────────────────
#  6. مهام Dropdown متخصصة
# ─────────────────────────────────────────────────────────────────────────────

DROPDOWN_TASKS: List[Task] = [
    # Generic dropdown interactions
    ("open the dropdown menu and select the first option",
     "https://the-internet.herokuapp.com/dropdown", "dropdown", 1),

    ("select the second option from the dropdown list",
     "https://the-internet.herokuapp.com/dropdown", "dropdown", 1),

    ("click to open a dropdown and choose an item from the list",
     "https://demoqa.com/select-menu", "dropdown", 2),

    ("select Blue from the color options dropdown",
     "https://demoqa.com/select-menu", "dropdown", 1),

    ("select Green from the color dropdown menu",
     "https://demoqa.com/select-menu", "dropdown", 1),

    ("open the group dropdown and select option A",
     "https://demoqa.com/select-menu", "dropdown", 2),

    ("select a car make from the dropdown: Volvo",
     "https://www.w3schools.com/tags/tryit.asp?filename=tryhtml_select",
     "dropdown", 1),

    ("select Opel from the cars dropdown",
     "https://www.w3schools.com/tags/tryit.asp?filename=tryhtml_select",
     "dropdown", 1),

    ("select multiple items from a multi-select list",
     "https://www.w3schools.com/tags/tryit.asp?filename=tryhtml_select_multiple",
     "dropdown", 2),

    # Country/language pickers
    ("select Egypt from the country dropdown",
     "https://demoqa.com/automation-practice-form", "dropdown", 1),

    ("select Arabic as the language preference",
     "https://www.wikipedia.org", "dropdown", 2),

    # Sort and filter dropdowns
    ("change the sort order to Price: Low to High",
     "https://juice-shop.herokuapp.com", "dropdown", 2),

    ("sort the results by newest first using the sort dropdown",
     "https://juice-shop.herokuapp.com", "dropdown", 2),

    ("filter the product list by category",
     "https://juice-shop.herokuapp.com", "dropdown", 2),
]


# ─────────────────────────────────────────────────────────────────────────────
#  7. مهام Checkbox & Radio متخصصة
# ─────────────────────────────────────────────────────────────────────────────

CHECKBOX_TASKS: List[Task] = [
    # Single checkbox
    ("check the remember me checkbox on the login page",
     "https://the-internet.herokuapp.com/login", "checkbox", 1),

    ("check the first checkbox on the checkboxes page",
     "https://the-internet.herokuapp.com/checkboxes", "checkbox", 1),

    ("uncheck checkbox 1 and check checkbox 2",
     "https://the-internet.herokuapp.com/checkboxes", "checkbox", 2),

    # Multiple checkboxes
    ("select all available options by checking all checkboxes",
     "https://demoqa.com/checkbox", "checkbox", 2),

    ("check only the Reading hobby checkbox",
     "https://demoqa.com/automation-practice-form", "checkbox", 1),

    ("check both Sports and Music hobby checkboxes",
     "https://demoqa.com/automation-practice-form", "checkbox", 2),

    ("check all three hobby checkboxes: Sports, Reading, and Music",
     "https://demoqa.com/automation-practice-form", "checkbox", 2),

    # Radio buttons
    ("select Yes radio button",
     "https://demoqa.com/radio-button", "checkbox", 1),

    ("click the Impressive radio button option",
     "https://demoqa.com/radio-button", "checkbox", 1),

    ("select male gender radio button",
     "https://demoqa.com/automation-practice-form", "checkbox", 1),

    ("select the other radio button option",
     "https://demoqa.com/automation-practice-form", "checkbox", 1),

    # Terms & conditions
    ("check the I agree to terms and conditions checkbox",
     "https://opencart.abstracta.us/index.php?route=account/register", "checkbox", 1),

    ("check the privacy policy agreement checkbox and continue",
     "https://opencart.abstracta.us/index.php?route=account/register", "checkbox", 2),

    ("accept the newsletter subscription checkbox",
     "https://opencart.abstracta.us/index.php?route=account/register", "checkbox", 1),

    # Shipping options
    ("select the express shipping radio button",
     "https://opencart.abstracta.us/index.php?route=checkout/checkout", "checkbox", 2),

    ("choose standard shipping option",
     "https://opencart.abstracta.us/index.php?route=checkout/checkout", "checkbox", 2),
]


# ─────────────────────────────────────────────────────────────────────────────
#  8. مهام Account Management — بعد تسجيل الدخول
# ─────────────────────────────────────────────────────────────────────────────

ACCOUNT_TASKS: List[Task] = [
    # Profile editing
    ("navigate to account profile settings page",
     "https://github.com/settings/profile", "account", 1),

    ("update the bio field in GitHub profile settings",
     "https://github.com/settings/profile", "account", 2),

    ("change the public email in GitHub profile",
     "https://github.com/settings/profile", "account", 2),

    ("fill the company field in GitHub profile",
     "https://github.com/settings/profile", "account", 2),

    ("fill the location field with Cairo, Egypt",
     "https://github.com/settings/profile", "account", 2),

    ("save the profile changes by clicking the update profile button",
     "https://github.com/settings/profile", "account", 1),

    # Password change
    ("navigate to password and authentication settings",
     "https://github.com/settings/security", "account", 1),

    ("fill the current password field in the password change form",
     "https://github.com/settings/security", "account", 2),

    ("fill new password and confirm new password fields",
     "https://github.com/settings/security", "account", 2),

    # Notifications settings
    ("navigate to notification settings",
     "https://github.com/settings/notifications", "account", 1),

    ("toggle email notifications checkbox for participating",
     "https://github.com/settings/notifications", "account", 2),

    # Logout
    ("log out from GitHub by clicking sign out",
     "https://github.com", "logout", 2),

    ("open the user menu and click sign out to log out",
     "https://github.com", "logout", 2),

    ("navigate to github.com, open profile dropdown, and sign out",
     "https://github.com", "logout", 3),

    # Stack Overflow account
    ("edit the Stack Overflow profile display name",
     "https://stackoverflow.com/users/edit/current", "account", 2),

    ("add a location to Stack Overflow profile",
     "https://stackoverflow.com/users/edit/current", "account", 2),

    ("fill the about me section in Stack Overflow profile",
     "https://stackoverflow.com/users/edit/current", "account", 2),

    # Reddit preferences
    ("change Reddit feed preference to best",
     "https://www.reddit.com", "account", 2),

    ("open Reddit preferences and change language",
     "https://www.reddit.com/prefs/", "account", 2),
]


# ─────────────────────────────────────────────────────────────────────────────
#  9. مهام HuggingFace — إنشاء حساب وإدارة
# ─────────────────────────────────────────────────────────────────────────────

HUGGINGFACE_TASKS: List[Task] = [
    # Signup
    ("register a new HuggingFace account by filling the signup form",
     "https://huggingface.co/join", "signup", 2),

    ("fill the username field during HuggingFace registration",
     "https://huggingface.co/join", "signup", 1),

    ("fill the email field with newuser@hf.test during signup",
     "https://huggingface.co/join", "signup", 1),

    ("fill the password field during HuggingFace account creation",
     "https://huggingface.co/join", "signup", 1),

    # Login
    ("log in to HuggingFace with username and password",
     "https://huggingface.co/login", "login", 1),

    ("enter email in HuggingFace login form",
     "https://huggingface.co/login", "form_fill", 1),

    # Model search with filters
    ("search for sentence-transformers model",
     "https://huggingface.co/models", "form_fill", 1),

    ("filter models by task text-classification",
     "https://huggingface.co/models", "search_filter", 2),

    ("filter models by language Arabic",
     "https://huggingface.co/models", "search_filter", 2),

    ("filter datasets by language English",
     "https://huggingface.co/datasets", "search_filter", 2),

    # Create model/dataset card
    ("click the New Model button to create a model repository",
     "https://huggingface.co/new", "form_fill", 1),

    ("fill the model name field",
     "https://huggingface.co/new", "form_fill", 1),

    ("select private visibility for the new model",
     "https://huggingface.co/new", "checkbox", 1),
]


# ─────────────────────────────────────────────────────────────────────────────
#  10. Wikipedia — إنشاء حساب
# ─────────────────────────────────────────────────────────────────────────────

WIKIPEDIA_TASKS: List[Task] = [
    # Login
    ("log in to Wikipedia with username and password",
     "https://en.wikipedia.org/w/index.php?title=Special:UserLogin", "login", 1),

    ("enter username in Wikipedia login form",
     "https://en.wikipedia.org/w/index.php?title=Special:UserLogin", "form_fill", 1),

    ("enter password in Wikipedia login form",
     "https://en.wikipedia.org/w/index.php?title=Special:UserLogin", "form_fill", 1),

    ("check the keep me logged in checkbox on Wikipedia",
     "https://en.wikipedia.org/w/index.php?title=Special:UserLogin", "checkbox", 1),

    # Signup
    ("create a Wikipedia account by filling the registration form",
     "https://en.wikipedia.org/w/index.php?title=Special:CreateAccount", "signup", 2),

    ("fill the username field during Wikipedia account creation",
     "https://en.wikipedia.org/w/index.php?title=Special:CreateAccount", "signup", 1),

    ("fill the password and confirm password fields on Wikipedia signup",
     "https://en.wikipedia.org/w/index.php?title=Special:CreateAccount", "signup", 2),

    ("fill the email field during Wikipedia registration",
     "https://en.wikipedia.org/w/index.php?title=Special:CreateAccount", "signup", 1),

    # Search
    ("search for Arabic Wikipedia page about machine learning",
     "https://ar.wikipedia.org", "form_fill", 1),

    ("change Wikipedia language to Arabic using the language switcher",
     "https://www.wikipedia.org", "dropdown", 2),
]


# ─────────────────────────────────────────────────────────────────────────────
#  11. PyPI — البحث والتصفية
# ─────────────────────────────────────────────────────────────────────────────

PYPI_TASKS: List[Task] = [
    ("search for requests package on PyPI",
     "https://pypi.org", "form_fill", 1),

    ("filter PyPI search results by framework Django",
     "https://pypi.org/search/", "search_filter", 2),

    ("filter by programming language Python 3",
     "https://pypi.org/search/", "search_filter", 2),

    ("sort PyPI search results by trending",
     "https://pypi.org/search/", "search_filter", 1),

    ("search for machine learning libraries on PyPI",
     "https://pypi.org/search/?q=machine+learning", "form_fill", 1),

    ("filter packages by topic Data Science",
     "https://pypi.org/search/", "search_filter", 2),
]


# ─────────────────────────────────────────────────────────────────────────────
#  12. مهام تدريب متنوعة إضافية — تغطي edge cases
# ─────────────────────────────────────────────────────────────────────────────

EDGE_CASE_TASKS: List[Task] = [
    # Empty form submission
    ("try to submit an empty login form and observe the error",
     "https://the-internet.herokuapp.com/login", "form_fill", 2),

    # Password fields
    ("fill the password field with a strong password Secur3P@ss!",
     "https://github.com/signup", "form_fill", 1),

    ("fill confirm password field to match the password",
     "https://demoqa.com/register", "form_fill", 2),

    # Phone number fields
    ("fill the phone number field with +20 1012345678",
     "https://demoqa.com/automation-practice-form", "form_fill", 2),

    # Date fields
    ("fill the date of birth field: day 15, month January, year 1995",
     "https://demoqa.com/automation-practice-form", "form_fill", 2),

    # Address forms
    ("fill the full address: building 5, street Ramses, city Cairo, zip 11511",
     "https://opencart.abstracta.us/index.php?route=checkout/checkout",
     "form_fill", 3),

    # File upload
    ("click the choose file button to upload a profile picture",
     "https://the-internet.herokuapp.com/upload", "form_fill", 2),

    # Multi-page forms
    ("proceed to the next step in the checkout wizard",
     "https://opencart.abstracta.us/index.php?route=checkout/checkout",
     "multistep", 2),

    ("click the continue button to go to the next form step",
     "https://opencart.abstracta.us/index.php?route=checkout/checkout",
     "multistep", 1),

    ("go back to the previous step in the form",
     "https://opencart.abstracta.us/index.php?route=checkout/checkout",
     "multistep", 2),

    # Alert/modal forms
    ("confirm the action by clicking OK in the confirmation dialog",
     "https://the-internet.herokuapp.com/javascript_alerts", "form_fill", 2),

    ("dismiss the alert dialog",
     "https://the-internet.herokuapp.com/javascript_alerts", "form_fill", 2),

    # Autocomplete
    ("type python in the search box and select from the autocomplete suggestions",
     "https://www.google.com", "form_fill", 2),

    ("use the autocomplete to find a city name Cairo",
     "https://demoqa.com/auto-complete", "form_fill", 2),

    # Captcha awareness (don't solve, just identify)
    ("identify and describe the captcha challenge on the page",
     "https://github.com/signup", "form_fill", 3),
]


# ─────────────────────────────────────────────────────────────────────────────
#  MASTER TASK LISTS
# ─────────────────────────────────────────────────────────────────────────────

ALL_COMPLEX_TASKS: List[Task] = (
    DEMO_FORM_TASKS
    + GITHUB_TASKS
    + REDDIT_TASKS
    + STACKOVERFLOW_TASKS
    + MULTISTEP_TASKS
    + DROPDOWN_TASKS
    + CHECKBOX_TASKS
    + ACCOUNT_TASKS
    + HUGGINGFACE_TASKS
    + WIKIPEDIA_TASKS
    + PYPI_TASKS
    + EDGE_CASE_TASKS
)

# مهام مجردة (goal, url) للتوافق مع dagger_tasks format
COMPLEX_DAGGER_TASKS = [(goal, url) for goal, url, _, _ in ALL_COMPLEX_TASKS]

# تصنيف حسب النوع
def get_tasks_by_type(task_type: str) -> List[Task]:
    return [t for t in ALL_COMPLEX_TASKS if t[2] == task_type]

def get_tasks_by_difficulty(difficulty: int) -> List[Task]:
    return [t for t in ALL_COMPLEX_TASKS if t[3] == difficulty]

def get_easy_tasks() -> List[Task]:
    return get_tasks_by_difficulty(1)

def get_medium_tasks() -> List[Task]:
    return get_tasks_by_difficulty(2)

def get_hard_tasks() -> List[Task]:
    return get_tasks_by_difficulty(3)

# مجموعات مخصصة للمراحل المختلفة
PHASE1_TASKS = [(g, u) for g, u, _, d in ALL_COMPLEX_TASKS if d == 1]
PHASE2_TASKS = [(g, u) for g, u, _, d in ALL_COMPLEX_TASKS if d <= 2]
PHASE3_TASKS = [(g, u) for g, u, _, _ in ALL_COMPLEX_TASKS]   # كل المهام


# ─────────────────────────────────────────────────────────────────────────────
#  STATS
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from collections import Counter

    print(f"\n{'='*60}")
    print(f"  BrowserMind — Complex Task Set")
    print(f"{'='*60}")
    print(f"  Total tasks : {len(ALL_COMPLEX_TASKS)}")
    print()

    by_type = Counter(t[2] for t in ALL_COMPLEX_TASKS)
    print("  By type:")
    for task_type, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"    {task_type:<20} {count:>3} tasks")

    print()
    by_diff = Counter(t[3] for t in ALL_COMPLEX_TASKS)
    print("  By difficulty:")
    for d, count in sorted(by_diff.items()):
        label = {1: "Easy  ", 2: "Medium", 3: "Hard  "}[d]
        print(f"    {label} (level {d})  {count:>3} tasks")

    print()
    by_domain = Counter()
    for _, url, _, _ in ALL_COMPLEX_TASKS:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace("www.", "")
        by_domain[domain] += 1

    print("  By site (top 10):")
    for domain, count in by_domain.most_common(10):
        print(f"    {domain:<45} {count:>3} tasks")

    print(f"{'='*60}\n")
